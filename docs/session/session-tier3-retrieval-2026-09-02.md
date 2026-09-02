# Session — Áp dụng Tier 3 gói Retrieval (union + RRF + chunk BM25 + eval harness)

- **Ngày**: 2026-09-02
- **Nguồn**: `docs/tier3-roadmap.md` §1–§3 (thuộc idea bundle `docs/human-ideas/my-idea/`)
- **Plan**: `~/.commandcode/plans/llm-wiki-tier3-retrieval.md` (có §7 đánh giá tác động R1–R15)
- **Tiếp nối**: `docs/session/session-tier1-tier2-okf-apply-2026-09-01.md`
- **Trạng thái**: hoàn tất implementation + verification. **Chưa commit.**

---

## 1. Quyết định phạm vi

Rẽ 3 câu hỏi trước khi code (các mục tier 3 lệch nhau từ rất rẻ tới migration phá vỡ tương thích):

1. **Phạm vi** = chỉ gói retrieval (§1 eval harness + §2 RRF + §3 chunk-BM25). KHÔNG làm OKF full conformance (`kind`→`type`, `.wiki/`), g3doc layout, registry.yml, Attested Computation, `[private]` dirs, export, migrate.
2. **Rerank ở skill layer**, không thêm dependency. `cross-encoder` vẫn nằm trong roadmap như mục deferred.
3. **Golden set là dữ liệu do người điền**: template + `eval/golden.toml` per-wiki; eval từ chối bịa số liệu khi file trống.

Không đụng content wiki: frontmatter contract, trust tier, pins, alerts, translate, **schema của `registry.toml`**, MCP write-path giữ nguyên → **không có migration dữ liệu**, `.wiki.db` là derived. (Về *nội dung* registry thật trên máy này: xem §7b.)

## 2. Thiết kế lõi

Fusion đổi từ **weighted sum** sang **RRF trên hạng**, vì `bm25()` không có thang cố định còn cosine ∈ [-1,1]; cộng thẳng làm kênh BM25 áp đảo.

| kênh | hạ tầng | tắt khi |
|---|---|---|
| `bm25_page` | FTS5 `pages_fts` (wiki + raw) | FTS5 không có |
| `bm25_chunk` | FTS5 `chunks_fts` (bảng mới trong `.wiki.db`) | `chunk_bm25=false` / chưa `reindex --full` |
| `vector_chunk` | `rag/.rag_index/{chunks.json,vectors.npy}` | `vector=false`, chưa build, thiếu model |

Ba quyết định kỹ thuật quan trọng nhất:

- **Chunk FTS nằm trong SQLite, không trong `base_rag/`** — `rag/index.py:build_index()` return sớm khi `vector=false` (mặc định của repo) và import numpy/fastembed ở top-level. Đặt ở đó là chết từ gốc.
- **Chunker tách thành `tools/chunking.py` dep-free, dùng chung cho cả 2 pipeline** — nếu không, chunk của BM25 và của vector khác ranh giới ⇒ fusion 2 kênh chunk vô nghĩa.
- **`fusion="weighted"` được GIỮ NGUYÊN đường code cũ** — không phải để tương thích, mà để `eval --compare` có baseline tái hiện công thức Tier 1.

Hệ quả từ phần đánh giá tác động (không phải ý tưởng ban đầu, sinh ra khi trace code):
`index.md`/`log.md` bị loại khỏi chunking ở **cả hai** pipeline. Lý do thực chứng: `watch.py:scan_wiki` reindex theo **mtime**, mà `log.md` đổi mỗi lần ingest → sẽ re-chunk mọi 5 phút; và log.md append-only biến mỗi entry thành một chunk, đẩy `log.md` lên top mọi query trùng keyword.

## 3. Implementation (7 phase)

### Phase 0 — 3 lỗi tiền quyết (tìm thấy khi trace, nằm ngay trên đường đi)
- **0a** `db.upsert_page`: `pages_fts` là external-content nhưng INSERT mà không phát `'delete'` ở nhánh UPDATE → cùng rowid tích nhiều bộ token, `bm25()` rank trên duplicate. Đọc `(content,title)` CŨ rồi phát `INSERT INTO pages_fts(pages_fts, rowid, ...) VALUES('delete',...)`.
- **0b** `llm-wiki lint --fix` **không tồn tại trong CLI** dù `README.md` đã tài liệu hóa và `lint.py` đã parse `--fix`. Thêm flag.
- **0c** `installer.centralized_server_env()` **pin** `WIKI_BM25_WEIGHT=0.5` / `WIKI_VEC_WEIGHT=0.5` / `WIKI_EMBED_MODEL=<builtin>` vào MCP entry. Vì precedence là env > TOML, ba key đó trong `.llm-wiki.toml` **bị vô hiệu khi search qua MCP nhưng vẫn có tác dụng qua CLI** → cùng wiki, hai kết quả. Bỏ cả 3 (giá trị pin ≡ builtin default nên ai không sửa TOML không đổi hành vi).

### Phase 1 — `base_tools/chunking.py` (mới)
Move `clean_body` / `split_long` / `chunk_markdown` / `TRANSLATED_SUFFIX_RE` từ `base_rag/index.py`; thêm `is_reserved()` (`index.md`/`log.md`/`readme.md`). Xóa `import re` thừa ở `base_rag/index.py`. Gom `TRANSLATED_SUFFIX_RE` về một chỗ cho `ingest.py` / `watch.py` / `reindex.py` (trước đây trùng 4 nơi).

### Phase 2 — `chunks_fts` + sync
- `db.init_db`: `CREATE VIRTUAL TABLE chunks_fts USING fts5(text, path UNINDEXED, chunk_idx UNINDEXED, page_id UNINDEXED)`. **Có chủ đích không dùng external-content**: `DELETE WHERE page_id=?` là đủ và đúng, đổi duplicate text lấy tính đơn giản.
- `search.sync_chunks(conn, pid, path, content, chunk_tokens)` — DELETE-then-INSERT theo page, chỉ `wiki/`, trừ reserved; **commit riêng** vì `upsert_page` đã commit trước đó.
- `db.delete_page` + `reindex` stale path + `lint.fix_missing_files` đều dọn `chunks_fts`.
- `reindex.SCHEMA_VERSION` 2→3: incremental skip page theo content-hash, nên **không bump thì wiki cũ không bao giờ có chunk**. `--check` in số chunk + "CHƯA build".

### Phase 3 — `search.py` viết lại (172 → ~600 dòng)
`_retrieval_settings()` trả **dict** (thay tuple), `_bool_env`, `rag_index_dir()` resolve per-call, `_fts_terms`/`_fts_and_query`/`_fts_or_query`/`_query_attempts`, `_fts_ranked`, `_rrf`/`rrf_fuse`, 3 hàm kênh, `_rrf_search`, `_weighted_search` (giống Tier 1), `sync_chunks`, `chunk_count`, `_warn_no_chunks`, `CHANNEL_ERRORS`.
- Bỏ **full-table-scan** `SELECT ... FROM pages` + pure-Python cosine từng page ở chế độ RRF → chỉ `WHERE id IN (...)`.
- Result thêm `matched_by` (kênh nào tìm ra) + `rank`; `snippet` ưu tiên text của chunk match → skill rerank không phải mở file.
- `weights` seed từ `bm25_weight`/`vec_weight` (RRF chỉ nhạy tỉ số → env cũ không gây lệch).
- Env mới: `WIKI_FUSION`, `WIKI_CHUNK_BM25`. `mode="structural"` rút khỏi vocabulary (chưa từng được implement).
- Config DEFAULTS sửa **cả hai** nơi: `config_file.py` + shim `base_tools/config_file.py`. Thêm `[retrieval.weights]` + `[eval]`.

### Phase 4 — MCP server
- `wiki_search` giữ signature `(query, top_k=8, wiki="")`; `top_k=0` → `top_n_final`. Merge cross-wiki đổi từ `sort by score` → **RRF trên hạng-per-wiki** + khử trùng `(wiki, path)` (trước đó không khử trùng); `_err` dict đặt CUỐI list (chúng không có `path`/`score`).
- `_provider()` trước đây resolve **trước vòng lặp multi-wiki** → model embedding của wiki cuối bị dùng cho mọi wiki. Sửa thành cache theo model + resolve per-wiki.
- `semantic_search`: `index_dir` qua `search.rag_index_dir()` (tôn trọng env per-wiki) thay vì hard-code; thêm `matched_by`.
- Legacy `mcp_server.py` không được cài → không sửa.

### Phase 5 — Eval harness
- `base_tools/eval.py` (mới): `llm-wiki eval [--k] [--compare] [--json] [--init] [--no-save] [-v]`. In bằng `print` + bảng tự kẻ (base venv không có `rich`).
- Profile `--compare`: `tier1-weighted` / `rrf-text` / `rrf+vector` (profile thiếu hạ tầng → `SKIPPED`, không tính).
- Metric macro-average P@k, R@k, MRR + `zero_recall_queries`. Verdict tự kết luận nên bật vector hay không.
- `eval/golden.toml` (TOML — không có YAML dep, `tomllib`/`tomli` try-except cho floor 3.10) đặt ở **root `eval/`**, KHÔNG dưới `wiki/`: `lint.py` quét mọi thư mục không-ẩn dưới `wiki/` như một domain → đặt trong `wiki/` sẽ ăn finding `domain-missing-index` ngay khi init.
- `paths.EVAL_DIR` (cả package + shim), `base.install_base` copy `templates/eval-golden.toml` → `~/.llm-wiki-base/templates/` để `eval --init` chạy được từ tools/, init personal/project copy template vào wiki (guard exists), `wiki-gitignore` thêm `eval/results.json`.
- `cli.py`: `@app.command("eval")` → `_run_base_tool("eval.py", ...)`.

### Phase 6 — Skill layer rerank + tài liệu
- `llm-wiki-query` + `wiki-project-research` viết lại quy trình: xin `top_k = 2 × top_n_final` → **rerank bằng LLM** chỉ dựa trên `title`/`snippet`/`matched_by` (không mở file) với 4 tiêu chí (đúng chủ đề > nhiều kênh > trust tier > page canonical) → cắt xuống `top_n_final`. Thêm section "Đo chất lượng retrieval" cho cả 2.
- `wiki-project-mcp` tool table cập nhật.
- `_schema.md` (Search viết lại + Eval operation), `AGENTS.md` (cấu trúc + reserved names + Search config + Tooling), `CLAUDE.md` (Query 8 bước + config TOML block + env), `README.md` (headline, cấu trúc thư mục, CLI, Config, **section "Retrieval & eval" mới**, **section "Nâng cấp từ bản trước" mới**, MCP table), `docs/init.md`, `docs/credits.md`, `docs/tier3-roadmap.md` (§1–3 → ✅ + mục 3b limitation + cross-encoder giữ deferred).

## 4. Bug tìm thấy NHỜ test (không phải lúc code)

Bốn lỗi này chỉ lộ ra khi chạy số liệu thật trên scratch wiki:

1. **Sanitizer phá identifier có dấu `-`**: bản cũ `re.sub(r"[^\w]+","",t)` **dính** `kumquat-xray-77` thành `kumquatxray77`, trong khi tokenizer unicode61 cắt thành `kumquat`/`xray`/`77` → mọi identifier gạch nối không bao giờ match. Sửa: tách term (`_fts_terms`).
2. **Chuỗi relax không bao giờ chạy**: `_fts_ranked` `return` ngay ở lượt đầu kể cả khi 0 dòng → query tiếng Việt có một stopword ("là", "gì") làm AND fail là mất hết. Đây là lý do eval ban đầu ra R@8=0.4/3 miss; sau sửa → R@8=0.9/0 miss. Attempt giờ: giữ nguyên → AND sanitize → OR.
3. **Thiếu `[:, None]` khi normalize theo hàng** (tôi port lại cùng lỗi ở 2 chỗ): `arr / norms` với norms shape `(N,)` broadcast sai trục → exception bị except nuốt → kênh vector **chết im lặng** và eval in ra số liệu trông hợp lệ nhưng không đo vector. Sửa ở `search._channel_vector_chunk` + `mcp_base_server.semantic_search`.
4. **`config show` nói dối**: in giá trị default/TOML nhưng dán nhãn `[env WIKI_FUSION]`. Giờ resolve + cast giá trị hiệu lực thật.

Từ lỗi (3) sinh ra cơ chế chống tái diễn: `search.CHANNEL_ERRORS` — kênh chết **vì lỗi** (khác "tắt vì cấu hình") được eval in `[ERROR] kênh bị tắt vì lỗi`. Khi test lại phát hiện cơ chế này báo **false alarm** (một lượt sanitize chạy sạch nhưng 0 kết quả bị tính là lỗi), siết lại bằng cờ `ran_cleanly`.

## 5. Verification (scratch wiki, `~/.llm-wiki-base/tools` deployed)

Wiki test: 10 page seed (1 page 15 section chứa term hiếm `kumquat-xray-77` ở giữa, `log.md` 9 entry, 2 domain index), repo của máy không bị đụng; MCP test dùng **registry tạm** trong scratchpad.

1. `python -m compileall src/llm_wiki` + `-W error::SyntaxWarning` — sạch.
2. `pip install -e .` + `llm-wiki base install` → `tools/chunking.py`, `tools/eval.py`, `templates/eval-golden.toml` có mặt.
3. `init personal --no-mcp`: tạo `eval/golden.toml`, `.llm-wiki.toml` key mới; `init project`: cùng. 12 module import OK.
4. **Reserved files không chunk**: `count(*) FROM chunks_fts WHERE path LIKE '%log.md' OR '%index.md'` = 0 ✓; `llm-wiki reindex --full` → 19 chunks DB == 19 chunks RAG → **2 pipeline cùng ranh giới** ✓.
5. **0a hết duplicate**: `upsert_page` 3 lần cùng page → `SELECT count(*) FROM pages_fts` = 10 = số page ✓; `DELETE FROM pages_fts WHERE pages_fts MATCH 'pins'` = 1 row ✓; `PRAGMA integrity_check` = ok.
6. **Chunk-BM25 chứng minh được giá trị**: query `kumquat-xray-77` → RRF đưa `rrf-fusion.md` lên #1 với snippet đúng đoạn kumquat (`via=[bm25_page, bm25_chunk]`); baseline weighted xếp `log.md` #1 ✗.
7. **Kênh vector thật sự hoạt động** (không chết im lặng): query tiếng Anh paraphrase "confidence level of knowledge written by AI" → weighted: MISS; rrf-text: `trust-tier` #2; rrf+vector: `trust-tier` **#1** với cả 3 kênh đồng thuận. `CHANNEL_ERRORS` rỗng.
8. **Baseline tái hiện**: `fusion="weighted"` vẫn ra thứ tự như code cũ cho 3 query spot-check ✓.
9. **Fallback tất định**: `DROP TABLE chunks_fts` → search vẫn chạy, chỉ còn `bm25_page`, log 1 lần nhắc `reindex --full` ✓. `vector=true` nhưng xóa `rag/.rag_index/` → kênh tắt, không raise.
10. **relax_recall**: `'note: trust tier'` (FTS5 parse `note:` thành column filter, lỗi cú pháp) vẫn recover qua lượt sanitize, trả kết quả, **không** báo lỗi kênh giả ✓. `'kumquat-xray-77'`, `'reindex content_hash'` match đúng.
11. **MCP**: `wiki_search(wiki="")` trên registry 2 wiki + 1 wiki hỏng → có `wiki` field, không trùng `(wiki,path)`, `_err` nằm CUỐI list ✓; `top_k=0` → `top_n_final` ✓; `semantic_search` trả kết quả + không còn `log.md`/`index.md` ✓; `wiki_lint` giữ nguyên API dict cũ ✓.
12. **Drift/rollout**: hạ `.index_meta.json` về `schema_version=2` → `reindex --check` in `schema_version: 2 -> 3` và `reindex` in warn `--full` ✓.
13. **Idempotent**: `reindex` lần 2 → "0 files indexed", chunks vẫn 19 ✓. Xoá 1 page + reindex → chunk của nó về 0 ✓.
14. **Eval**: `--compare` in bảng 3 profile + Δ + verdict; `relevant` trỏ path không tồn tại → cảnh báo tường minh (không âm lặng tính điểm sai) ✓; thiếu golden → hướng dẫn `--init`, exit 0 ✓; read-only ✓.
15. **Compat 2 chiều**: code cũ (`git show HEAD`) chỉ SELECT `pages`/`pages_fts` → mở DB mới vô sự ✓.
16. `llm-wiki lint` trên wiki vừa init → không có `domain-missing-index` cho `eval/` ✓ (chứng minh quyết định đặt golden ở root).
17. `config show` in đúng sub-table `[retrieval.weights]`, `[eval]` + giá trị hiệu lực khi set env ✓.
18. **Vector cache** (`_VECTOR_CACHE`, key = path+mtime+size của `chunks.json`/`vectors.npy`): kết quả cold == warm (đo được qua 2 lần `hybrid_search` liên tiếp trong 1 process), 1 entry được giữ, `eval --compare` không còn parse lại cả `chunks.json` 3 lần/query ✓.

Số liệu tổng trên wiki toy (10 page, 5 query vàng tự soạn — **chỉ là smoke test, không phải bằng chứng về chất lượng**):

```
profile         N  P@8    R@8  MRR     miss
tier1-weighted  5  0.125  0.9  0.9     0
rrf-text        5  0.125  0.9  0.8667  0
rrf+vector      5  0.125  0.9  0.85    0
```

Recall bão hoà ở scale này nên Δ≈0; phần thắng của RRF/chunk nằm ở **thứ tự** (mục 6, 7), không ở R@8 của bộ query từ điển. Kết luận trung thực: gói này chưa — và không thể — được chứng minh là tốt hơn trên corpus 10 page.

### 5b. Đo trên wiki THẬT `wiki-test` (cùng session, sau khi fill golden set)

Wiki của người dùng: domain `expo-router`, 21 page / 28 chunk. Điền 18 query vàng
**candidate** vào `eval/golden.toml` (template cũ backup ở `golden.toml.bak-template-tier3`).
Trước khi đo phải rebuild rag index: index cũ từ 2026-09-01 còn chứa chunk của
`index.md`/`log.md` (50 chunk → dựng lại còn **28 chunk == đúng số `chunks_fts`**, xác nhận
2 kênh cùng ranh giới trên dữ liệu thật). Ghi chú: `reindex` với `vector=false` return trước
bước build RAG → muốn có rag index phải bật `vector` lúc reindex (đã làm tạm rồi trả config).

```
profile         N   P@8     R@8     MRR     miss
tier1-weighted  18  0.1667  0.8611  0.8274  0
rrf-text        18  0.1875  0.9167  0.8518  1   <- q06
rrf+vector      18  0.1944  0.9722  0.8981  0
```

Ba kết luận (một cái bác bỏ giả thuyết của chính tôi):

1. **Regression thật của RRF text-only**: q06 ("điều hướng bằng lệnh từ code thay vì
   component" — paraphrase cố tình cài) mất. `router.md` hạng **7 ở cả 2 kênh**, fused →
   hạng **9**, rớt cutoff 8; page hạng 1 ở một kênh + hạng 11 ở kênh kia vượt lên. Tính
   chất kinh điển của RRF khi weight bằng nhau, không phải bug.
2. **`rrf_k` không phải đòn bẩy**: sweep 20/40/60/100/150/250 cho số liệu **giống hệt**.
   Giả thuyết "tăng k favour đồng thuận" bị data phủ định trên corpus này.
3. **Đòn bẩy thật là `weights.bm25_page`**: `2.0` cứu q06 (R@8 0.9722) nhưng **MRR tụt
   còn 0.8310** (dưới cả rrf-text). `vector=true` đạt cả hai → đã bật cho wiki-test,
   lý do + số liệu ghi thẳng vào comment trong `wiki-test/.llm-wiki.toml`.

**Giá trị của phép đo này có giới hạn**: `relevant` do AI phán, nên nó đủ sức chỉ ra
regression (regression đến từ thứ tự, không phụ thuộc phán đoán), nhưng chưa đủ để kết
luận "vector tốt hơn cho bạn" — cần người thay query bằng câu hỏi thật.

**Ghi chú sự cố**: một lần gọi `llm-wiki reindex --full` chết `SIGABRT` (từ typer: `died with <Signals.SIGABRT: 6>`), không tái hiện được 3 lần sau đó. Nghi vấn: onnxruntime/fastembed abort khi process trước đó (seed script + `eval --compare`) còn giữ model trong RAM. DB nguyên vẹn sau đó (`integrity_check` ok, `pages_fts` = số page). Không phải lỗi logic Tier 3, nhưng theo dõi nếu tái diễn.

## 6. Files changed

**Modified (29)**:
- runtime `src/llm_wiki/base_tools/`: `search.py` (+531, viết lại), `db.py`, `reindex.py`, `ingest.py`, `lint.py`, `watch.py`, `mcp_base_server.py`, `config_file.py`, `paths.py`
- runtime `src/llm_wiki/`: `base_rag/index.py`, `config_file.py`, `paths.py`, `cli.py`, `installer.py`, `base.py`, `init_personal.py`, `init_project.py`
- template: `templates/llm-wiki.toml`, `templates/wiki-gitignore`, `templates/agents/{_schema,AGENTS,CLAUDE}.md`
- skills: `skills/personal/llm-wiki-query/SKILL.md`, `skills/project/{wiki-project-research,wiki-project-mcp}/SKILL.md`
- docs: `README.md`, `docs/tier3-roadmap.md`, `docs/init.md`, `docs/credits.md`

**New (4)**: `src/llm_wiki/base_tools/chunking.py`, `src/llm_wiki/base_tools/eval.py`, `src/llm_wiki/templates/eval-golden.toml`, `docs/session/session-tier3-retrieval-2026-09-02.md`

Tổng: **+1146 / −291** trên 29 file sửa (chưa tính 4 file mới), riêng `search.py` chiếm +531. Không thêm dependency; `pyproject.toml` và `requirements.txt` không đổi (`base_tools/*` đã được force-include và copy tự động).

Không đổi: `.gitignore` của repo, `_schema.md` ở repo root, frontmatter contract, MCP write-path, `wiki_lint` API, `pyproject.toml`/`requirements.txt`.

## 7. Ghi chú vận hành

**3 bước thủ công sau khi pull** (mỗi wiki đã tồn tại):

```bash
pip install -e . && llm-wiki base install           # 1. sync code
cd <wiki-cũ> && llm-wiki reindex --full             # 2. build chunks_fts + sửa FTS duplicate rows
cd <wiki-cũ> && llm-wiki init personal -c claude    # 3. refresh skills + MCP env (trả lời yes)
```

- Bước 2 **bắt buộc một lần**: không chạy thì kênh `bm25_chunk` im lặng trống, search vẫn chạy nhưng thiếu một kênh. `reindex --check` sẽ báo "chunk index CHƯA build".
- Bước 3: `init` hỏi Confirm vì thư mục không rỗng → trả lời yes. `.llm-wiki.toml` **không bị ghi đè** (guard exists) → cấu hình cũ giữ nguyên, key mới tự lấy default. Skills là bản copy nên phải refresh mới có bước rerank.
- **Thứ tự rank của `wiki_search` ĐỔI** so với bản trước (RRF + chunk) và đổi này là **mặc định**, không cần user sửa config. Rollback 1 dòng: `fusion = "weighted"` trong `.llm-wiki.toml` (hoặc `WIKI_FUSION=weighted`).
- MCP entry cũ trên máy vẫn còn 3 env pin cho tới khi chạy lại `init` (chỉ `install_centralized_mcp` mới ghi lại entry; `base install` không đụng MCP config).
- `semantic_search` không còn trả chunk của `index.md`/`log.md` (chủ đích).
- `pages.embedding` vẫn được ghi nhưng RRF không đọc (chỉ weighted mode dùng) → giữ để baseline đo được; candidate bỏ nếu không ai rollback.

### 7b. Trạng thái máy này sau session

- **Bước 1 ĐÃ chạy trên máy này**: `pip install -e .` + `llm-wiki base install` → `~/.llm-wiki-base/tools/` (kèm `chunking.py`, `eval.py`) và `~/.llm-wiki-base/templates/eval-golden.toml` đã là bản mới. Vì vậy MCP server khởi động lại sẽ chạy code mới ngay — kể cả khi wiki chưa làm bước 2 (lúc đó channel `bm25_chunk` còn trống, có warning nhắc).
- **Bước 2 và 3 CHƯA chạy** cho 2 wiki thật đang có trong `~/.llm-wiki-base/registry.toml`: `wiki-test` (`~/developer/repos/per-projects/wiki-test`) và `wiki` (`~/developer/repos/per-projects/wiki-project-test/wiki`).
- Toàn bộ test chạy trên wiki tạm trong scratchpad + **registry tạm** (`LLM_WIKI_BASE_DIR=<scratch>/t3base`) → không đọc/ghi DB của 2 wiki thật.
- **Side effect đã xảy ra và đã dọn**: `llm-wiki init` tự gọi `add_wiki`, nên 4 wiki test (`t3wiki`, `t3wiki2`, `project-wiki`/`t3proj`, `t3final`) bị ghi vào registry THẬT. Đã `llm-wiki wiki remove` cả 4 + xoá folder tạm; `registry.toml` trở về đúng 2 entry ban đầu. → Bài học cho code: `init` không có cờ `--no-register`, nên test init bắt buộc phải trỏ `LLM_WIKI_BASE_DIR` ra ngoài từ đầu (các test MCP làm đúng thế, các test init thì không).

### 7c. Lệnh tái hiện bộ kiểm tra

```bash
# wiki test: seed 10 page (1 page 15 section chứa term hiếm ở giữa + log.md 9 entry)
mkdir -p /tmp/t3 && cd /tmp/t3 && llm-wiki init personal --here --name t3 --no-mcp --force
# ... viết page, wiki/log.md ...
export WIKI_ROOT=$PWD
llm-wiki reindex --full && llm-wiki reindex --check
sqlite3 wiki/.wiki.db "select path,count(*) from chunks_fts group by path"   # log.md/index.md phải absence
sqlite3 wiki/.wiki.db "select (select count(*) from pages_fts),(select count(*) from pages)"  # phải bằng nhau
llm-wiki eval --compare -v
llm-wiki lint ; llm-wiki config show
```

**Chưa commit.** Branch `feature/tier1-tier2-okf-apply`.

## 8. Việc còn mở

1. **Người duyệt `wiki-test/eval/golden.toml`**: 18 query là AI soạn từ nội dung thật,
   `relevant` là phán đoán của AI. Thay `query` bằng câu hỏi thật (lấy từ history phiên +
   `wiki/log.md`), sửa `relevant` — chỉ lúc đó các con số ở §5b mới là bằng chứng, không
   phải tín hiệu tự tham chiếu.
2. `wiki-test` đã bật `vector = true` kèm lý do + số liệu trong comment config.
   `wiki-project-test/wiki` **vẫn chờ** bước 2+3 (`reindex --full` + `init project -c claude`).
3. `wiki/log.md` vẫn là *page* → vẫn xuất hiện trong `bm25_page`: hướng xử lý
   `[retrieval] exclude_from_index` — đã ghi vào `docs/tier3-roadmap.md` §3b.
4. Cân nhắc port 18 mục verification thành test suite có thể lặp lại (repo vẫn chưa có pytest).
   Riêng `rrf_sweep` (quét `rrf_k`/weights) đáng giữ lại dưới dạng script đo — nó là thứ
   đã phủ định giả thuyết của tôi trong 30 giây thay vì một buổi tối.
5. Thêm cờ `--no-register` (hoặc cho phép override registry path) vào `llm-wiki init` để
   test init không làm bẩn registry thật — hệ quả trực tiếp của §7b.
6. Cross-encoder rerank trong Python chỉ cần khi wiki được dùng ngoài AI tool
   (dashboard/script) — hiện vẫn deferred.
