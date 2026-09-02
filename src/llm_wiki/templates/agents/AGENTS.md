# LLM Wiki — Schema & Conventions

Bạn là **wiki maintainer**. Con người cung cấp nguồn, câu hỏi, review. Bạn làm mọi thứ còn lại: đọc, tóm tắt, cross-reference, lint, bookkeeping. Wiki là artifact tích luỹ (compounding) — compile 1 lần, maintain mãi.

## Cấu trúc 3 đối tượng

- `raw/inbox/` — staging, file mới chờ ingest (mutable khi người thả vào).
- `raw/` — **local cache** sau ingest (cả URL + no-URL). **Có thể xoá tùy ý** — provenance nằm trong `sources:` field của wiki page. Gitignored mặc định.
- `wiki/` — markdown do bạn sinh/maintain. Bạn sở hữu layer này. **Đây là knowledge thực sự**, persistent + cross-linked.
- `wiki/.proposals/` — staging cho human-gated edits (qua MCP `wiki_propose_edit`).
- `wiki/alerts/` — hàng đợi gap từ review (mâu thuẫn, stale, trust gap, pin conflict) — pseudo-domain, frontmatter `domain: alerts, kind: alert, status: open|closed`.
- `wiki/pins.yml` — sửa tay của human (claim + anchor), sống sót qua regenerate. Ingest/consolidate KHÔNG ghi đè section mà pin `active` bám vào.
- `wiki/index.md` / `wiki/log.md` — **reserved names**: điều hướng + lịch sử. Vẫn là page (search được) nhưng **không bao giờ được chunk** (log.md append-only sẽ áp đảo kết quả tìm theo chunk).
- `eval/golden.toml` — bộ query vàng để đo retrieval (`llm-wiki eval`). **Dữ liệu, COMMIT**. `eval/results.json` — lịch sử đo, gitignored.
- `AGENTS.md` (file này) — schema: quy ước + workflow.

**Provenance semantics (diverges từ Karpathy gist):**

Karpathy coi `raw/` là "source of truth" immutable. Chúng ta không — vì:
- Wiki page đã được curated (compacted, deduplicated, cross-referenced) là dạng knowledge "lâu dài" hơn raw.
- URL gốc trong `sources:` là primary truth (host bên thứ 3, không bị user xoá).
- `raw/` chỉ là LRU cache cho LLM re-read khi cần verify.
- User xoá `raw/` → vẫn verify được qua URL re-fetch.
- User pin source quan trọng: `git add -f raw/<file>`.

## Domain (top-level folder dưới `wiki/`)

Số lượng **không cố định**. Domain = top-level folder ngay dưới `wiki/`, tên do agent auto-detect từ nội dung raw (kebab-case). Mỗi domain có `index.md` riêng + page theo **kind** (semantic role): `entity/`, `concept/`, `source/`, `task/`. Sub-folder tuỳ ngữ cảnh.

**Naming rule:** 1 framework/library rõ ràng → `expo-ecosystem`; 1 giáo trình → `minna-no-nihongo`; 1 dự án nội bộ → `my-project`; lĩnh vực rộng → tạo domain mới với tên mô tả.

Ví dụ path: `wiki/projects/task/2026-08-fix-auth.md`, `wiki/languages/vocab/minna-no-nihongo-bai-26.md`, `wiki/expo-ecosystem/concept/file-based-routing.md`, `wiki/goxviet/entity/goxviet.md`.

## Quy ước page

- Frontmatter YAML: `title`, `domain` (top-level folder), `kind` (source|concept|entity|task|alert), `tags`, `sources`, `updated`, `status` (draft|active|done|stale|planned|deprecated|superseded), `confidence` (legacy).
- **Trust fields (khuyến nghị)**: `generated: {by, at}` (ai sinh); `verified: {by: "human:<id>", at}` — vắng = unverified. **Duyệt = set verified** qua `llm-wiki verify <path> --by <id>` (dùng chung personal + project). AI KHÔNG tự set `verified`. Optional: `stale_after`, `x_owner`, `x_supersedes`.
- **`sources:` 2 dạng** (dual-format): flat list `[<url>...]` (legacy) HOẶC list-of-dicts `{id, resource, title}` + per-claim citation `[^id]` footnote kèm trích verbatim (chi tiết `_schema.md`).
- **Chống fork**: trước khi tạo page mới, tra DB page `status: planned` cùng slug → update, không create.
- Mọi claim quan trọng mang provenance: link về `raw/` (URL) hoặc `[[wiki page]]` hoặc footnote `[^id]`.
- **Wikilink format:** chỉ dùng `[[wiki/<domain>/<kind>/<slug>]]` (full path). KHÔNG dùng markdown link bọc wikilink kiểu `[text]([[path]])` — Obsidian không render đúng. Muốn custom text → dùng alias: `[[path|Custom Text]]`.
- Task page có trường: `status` (todo|doing|done|blocked), `priority`, `assignee`, `due`, `depends_on`.
- Kanban = `wiki/projects/kanban.md`, bảng 3 cột (Todo / Doing / Done), mỗi dòng link tới task page.
- **Backwards-compat:** page cũ chỉ có `category: <folder>` → tự infer `domain`/`kind` từ path. Agent sửa page cũ nên bổ sung frontmatter mới.

## Global runtime vs per-wiki data

- **Global runtime** ở `~/.llm-wiki-base/` (set qua `llm-wiki base install`, override path bằng env `LLM_WIKI_BASE_DIR`). Chứa `tools/`, `rag/`, `scripts/`, `.venv/`, `requirements.txt` — share giữa mọi wikis.
- **Per-wiki data** ở folder riêng (vd `my-wiki/`, `<project>/project-wiki/`). Chỉ chứa `raw/`, `wiki/`, `rag/.rag_index/`, `.env`, `.llm-wiki.toml`. KHÔNG có `tools/`, `rag/`, `scripts/`, `.venv/`.
- CLI wrapper (`llm-wiki ingest/reindex/lint/watch`) tự detect wiki dir qua `WIKI_ROOT` env hoặc cwd, gọi global base.
- Khi agent maintain wiki, chạy CLI wrapper hoặc `python <base>/tools/<tool>.py` trực tiếp. KHÔNG assume tools/ ở trong wiki dir.

## Operations

### Ingest
1. Source đến `raw/inbox/` — do con người thả, `scripts/extract_*.py` tạo, hoặc **AI khác nạp qua MCP `wiki_submit`** (dự án/task/tài liệu). Báo xử lý.
2. Bạn đọc source, **auto-detect domain** (xem "Naming rule" ở trên). Tạo folder `wiki/<domain>/` nếu chưa có.
3. Viết summary page vào `wiki/<domain>/source/<slug>.md` với frontmatter `domain: <name>`, `kind: source`.
   - **Nguồn (sources field):** Nếu raw file có `source` field là URL → dùng URL. Nếu không có URL → dùng `[]` (vì path local sẽ drift khi file rename/move).
4. Update entity/concept pages liên quan trong cùng domain (có thể chạm 10-15 page).
5. **Auto-translation (nếu enabled)**: đọc `<wiki-root>/.llm-wiki.toml`. Nếu `[translate].enabled = true` và `langs` không rỗng → với mỗi lang trong `langs`, **invoke skill `llm-wiki-translate`** để tạo file `<slug>.<lang>.md` song song source. KHÔNG tự dịch trong ingest — để skill dùng LLM của AI tool đang chạy.
6. Update `wiki/<domain>/index.md`. Nếu domain mới → tạo mới + insert row vào `wiki/index.md` (top-level). **Count pages chính xác** = `find wiki/<domain> -name "*.md" | wc -l` (KHÔNG đoán). Mô tả lấy từ dòng đầu tiên sau H1 trong `wiki/<domain>/index.md`.
7. Insert vào `wiki/log.md` (reverse-chronological, mới nhất trên). Format entry: header `## [YYYY-MM-DD HH:MM:SS] <op> | <title>` (op ∈ `ingest|review|consolidate|verify|wiki_lint|migrate|fix`), body bullets `- source:` / `- sources:` / `- tạo:` / `- update:` / `- skipped:` (chỉ viết action thực sự có). Ngày lấy từ frontmatter `updated` của source page, giờ tại thời điểm ingest.
8. Index vào search DB (CLI maintainer: `.venv/bin/python tools/ingest.py <path>`). KHÔNG qua MCP. Bản dịch `*.lang.md` bị skip (rule `TRANSLATED_SUFFIX_RE`).
9. Move source: cả URL + no-URL đều → `raw/` (local cache). Phân biệt provenance chỉ trong `sources:` frontmatter.

### Query
- Hỏi → định tuyến `index.md` → `wiki_search` (union + RRF, `top_k` rộng hơn `top_n_final`) → **rerank bằng LLM** rồi mở `top_n_final` page → tổng hợp + cite. Chi tiết: skill `llm-wiki-query`.
- Câu trả lời hay (so sánh, phân tích, connection) → file ngược lại thành page mới.
- Nghi ngờ chất lượng tìm kiếm → `llm-wiki eval --compare` (đọc `eval/golden.toml`).

### Lint (định kỳ — TẤT ĐỊNH)
Chạy `llm-wiki lint` (wrapper gọi global `tools/lint.py`). Checks deterministic:
- orphan page (không inbound link), broken wikilink (target không tồn tại), missing file (CRITICAL).
- missing-frontmatter, status-vocab, timestamp-format (`updated` = `YYYY-MM-DD`; `stale_after`/`verified.at` = ISO-8601).
- footnote-sources-match (`[^id]` ↔ `sources[].id`), stale-after-passed.
- missing-index-entry / domain-missing-index → `llm-wiki lint --fix` tự thêm (additive).
- pin-orphan (pin trong `wiki/pins.yml` mất concept/anchor → report human, không tự xoá).
- `sources-no-local-path` (`raw/inbox/...` trong sources:), `body-no-raw-inbox-wikilink`.
- dense-bullet / indent-depth / banned-terms (từ `[lint]` trong `.llm-wiki.toml`, advisory).

### Review (định kỳ — SINH SINH, sau lint)
Chạy skill `llm-wiki-review` (project: `wiki-project-review`) khi quá `[review].interval_days` (watermark `wiki/.review_state.json`; watch in `[review] due` khi hết hạn). Checks semantic:
- contradiction giữa pages / wiki ↔ code (model quyết → báo con người, **không** tự ghi edge).
- stale claim (quá `stale_after`, bị source mới supersede), stale code reference (project).
- khái niệm thiếu, trust gap (canonical để draft/unverified lâu), pin conflict.
- Gaps → `wiki/alerts/<slug>.md` (`kind: alert, status: open, last_seen`); không nêu lại 2 lần liên tiếp → tự đóng (`status: closed`).

### Consolidate (định kỳ)
Chạy skill `llm-wiki-consolidate` (project: `wiki-project-consolidate`): gộp log entries + mẩu rải rác thành concept canonical.
- Chỉ raw → concept; additive merge; tái grounding; **distill-verify** (citation set không co lại).
- Trùng → `status: superseded` + `x_supersedes`; tôn trọng pins; đổi judgment → `--unverify` chờ human duyệt.

### Auto-translation (optional)

Wiki song ngữ: mỗi source page có thể có bản dịch song song `<slug>.<lang>.md`. Bản dịch:
- Cùng frontmatter keys (sources, kind, updated, ...).
- Body dịch 100% tương đương (no paraphrase, preserve code/URL/term).
- **KHÔNG vào DB/RAG** (skip rule `*.lang.md`).

Setup (ghi vào `.llm-wiki.toml` ở wiki root):
```toml
[translate]
enabled = true
langs = ["vi", "ja"]
```

CLI:
```bash
llm-wiki translate enable --lang vi --lang ja
llm-wiki translate status
llm-wiki translate disable
llm-wiki translate check --lang vi   # verify đồng bộ
```

Khi enabled, **ingest skill** (sau bước 5) tự gọi **skill `llm-wiki-translate`** để dịch page vừa tạo sang mỗi target lang. Skill dùng **LLM của AI tool đang chạy** (Claude Code → Claude, OpenCode → provider). KHÔNG cần API key riêng.

Translation tốn token — cảnh báo user nếu `langs` dài (>5) hoặc N sources lớn.

## Nguyên tắc an toàn
- **AI proposes, human decides.** Edit trực tiếp chỉ với write re-derivable (index, log). Write asserting fact / irreversible → qua `wiki_propose_edit` (staging, chờ sign-off).
- Contradiction là report cho người, không materialize thành edge trên lời model.
- Provenance bắt buộc. Không claim không dẫn nguồn.
- **Copied state drift:** wiki page KHÔNG chứa value move-able (SHA, line count, mtime, count tuyệt đối). Values nằm trong frontmatter (mtime) hoặc tooling đọc live. Cite value chỉ khi claim về quá khứ (history) hoặc value phụ thuộc downstream đã nêu tên.

## Search & retrieval config
- Scale nhỏ: `index.md` đủ.
- **Union retrieval + RRF**: `wiki_search` chạy 3 kênh độc lập — `bm25_page` (FTS5 `pages_fts`), `bm25_chunk` (FTS5 `chunks_fts` trong `.wiki.db`), `vector_chunk` (`rag/.rag_index/`) — rồi gộp bằng **RRF trên hạng** (không cộng thẳng score). Mỗi kết quả có `matched_by` + `rank` + `snippet` (có thể là chunk text → đủ để CHỌN page, không đủ để trả lời).
- **Rerank là việc của skill** (`llm-wiki-query` / `wiki-project-research`) khi `[retrieval].rerank = "llm"`: xin `top_k` rộng hơn (`2 × top_n_final`), chấm bằng title/snippet/matched_by, rồi mới mở `top_n_final` page. Không thêm reranker model vào code.
- **Không chunk**: file reserved `index.md`/`log.md` (log.md append-only sẽ áp đảo kết quả) + bản dịch `*.lang.md` + frontmatter + footnote verbatim.
- **Fallback tất định**: thiếu model / chưa build chunk → tự tắt từng kênh, vẫn chạy BM25. `fusion = "weighted"` = hành vi cũ (rollback 1 dòng, cũng là baseline để A-B).
- **Đo trước khi bật vector**: `llm-wiki eval --compare` → P@k / R@k / MRR cho 3 profile. Query vàng ở `eval/golden.toml` (commit), kết quả ở `eval/results.json` (gitignored).
- **Behavior config nằm ở `.llm-wiki.toml`** (wiki root, commit): `[retrieval]` (`mode`, `fusion`, `rrf_k`, `chunk_bm25`, `vector = false` mặc định, `rerank`, `chunk_tokens`, `top_k_bm25`, `top_k_vector`, `top_n_final`, `relax_recall`, `[retrieval.weights]`), `[eval]`, `[review]`, `[lifecycle]`, `[lint]`. Env override: `WIKI_BM25_WEIGHT`, `WIKI_VEC_WEIGHT`, `WIKI_FUSION`, `WIKI_CHUNK_BM25`, `WIKI_EMBED_MODEL` (installer KHÔNG pin chúng trong MCP entry nữa — pin ở đó làm TOML bị vô hiệu).
- Xem effective config: `llm-wiki config show`.
- Semantic chunk-level vector: `rag/index.py` build `rag/.rag_index/` (tăng dần theo content-hash), query MCP `semantic_search`.
- Wiki cũ nâng cấp lên bản có `chunks_fts`: chạy `llm-wiki reindex --full` một lần (không thì kênh `bm25_chunk` im lặng trống).

## MCP bridge (cho AI khác kết nối wiki)
MCP = cầu nối, **KHÔNG** viết thẳng wiki:
- Đọc / tìm kiếm: `wiki_search`, `semantic_search`, `wiki_read`, `wiki_list`, `list_raw_source`, `read_raw_source`.
- Nạp context (WRITE duy nhất, có kiểm soát): `wiki_submit(title, content, domain, source)` → `raw/inbox/`.
- Đề xuất (staging): `wiki_propose_edit(path, content)` → `wiki/.proposals/`, chờ người sign-off.
- Index / ingest lên wiki là việc **maintainer** (CLI `tools/ingest.py` / skill `llm-wiki-ingest`), không qua MCP.

## Tooling
- `scripts/` — extract nguồn: `extract_url.py` (trafilatura), `extract_pdf.py` (PyMuPDF), `extract_youtube.py`. Thả kết quả vào `raw/inbox/`, watch tự ingest.
- `tools/paths.py` — central path constants. Mọi file trong `tools/` + `rag/` + `scripts/` import từ đây.
- `tools/chunking.py` — semantic chunker **dùng chung** bởi chunk-BM25 (`chunks_fts`) và chunk-vector (`rag/.rag_index/`). 2 pipeline phải cùng ranh giới chunk thì RRF mới có nghĩa.
- `tools/search.py` — union retrieval + RRF fusion + chunk sync (`sync_chunks`). Điểm duy nhất đọc config `[retrieval]` (per-call).
- `tools/watch.py` — daemon: quét `raw/inbox/`, ingest, move sang `raw/`, định kỳ `wiki_lint`.
- `tools/ingest.py <path>` — index 1 file thủ công.
- `tools/reindex.py` — reindex DB (kèm chunk) + RAG **tăng dần theo content-hash**; `--full` rebuild toàn bộ (cần 1 lần sau upgrade); `--check` dry-run.
- `tools/eval.py` — đo retrieval trên query vàng: P@k / R@k / MRR, `--compare` nhiều profile. Read-only với wiki.
- `rag/index.py` — build semantic chunk vector index.
