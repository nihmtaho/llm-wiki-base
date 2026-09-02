# LLM Wiki — Runbook cho AI Agent

Schema canonical: `AGENTS.md`. Quy tắc: `_schema.md`.

## Vai trò

Wiki maintainer. Đọc, tóm tắt, cross-reference, lint, bookkeeping. KHÔNG tự ý claim fact mà không có provenance.

## Khởi tạo nhanh (fresh repo)

```bash
# Từ repo root
.venv/bin/python -m pip install -r requirements.txt
export WIKI_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2  # on-device, đa ngôn ngữ
```

Nếu repo dùng template: `bash init.sh` thay cho 2 lệnh trên.

## Ingest (8 bước)

1. Source đến `raw/inbox/`. Trigger: human drop, `scripts/extract_*.py`, MCP `wiki_submit`, hoặc `tools/watch.py` daemon.
2. Đọc source, **auto-detect domain** theo naming rule (kebab-case). Tạo `wiki/<domain>/` nếu chưa có.
3. Viết summary page → `wiki/<domain>/source/<slug>.md` với frontmatter `domain`, `kind: source`.
   - URL có sẵn trong raw frontmatter → dùng URL trong `sources:`.
   - Không có URL → `sources: []` (KHÔNG dùng path local — vi phạm copied-state rule).
4. Update entity/concept pages liên quan (1 source có thể chạm 10-15 page).
5. Update `wiki/<domain>/index.md`. Nếu domain mới → tạo + insert row vào `wiki/index.md` (top-level). Page count = `find wiki/<domain> -name "*.md" | wc -l` (chính xác, không đoán).
6. Insert vào `wiki/log.md` (reverse-chronological). Format: `## [YYYY-MM-DD HH:MM:SS] <op> | <title>` với `op ∈ ingest|review|consolidate|verify|wiki_lint|migrate|fix`. Body bullets chỉ viết action thực sự có.
7. Index DB: `.venv/bin/python tools/ingest.py <path>` (KHÔNG qua MCP).
8. Move source: cả URL + no-URL đều → `raw/` (local cache, có thể xoá). Watch daemon tự động.

## Query

1. **Union search**: MCP `wiki_search(query, top_k=16)` — 3 kênh (BM25 page ∪ BM25 chunk ∪ vector chunk) gộp bằng **RRF**. `top_k` ở đây chỉ là **số lượng bạn xin về**, không phải số page sẽ đọc.
2. **Rerank bằng LLM** (`[retrieval].rerank = "llm"`): chấm qua `title` + `snippet` + `matched_by`, chọn `top_n_final` (mặc định 8) để mở. Không mở file lúc chấm.
3. `wiki_read` các page đã chọn. `matched_by` nhiều kênh + `verified.by: human:*` = tin hơn.
4. Semantic chunk thô: `semantic_search(query, top_k=6)` — chỉ để dò, **không trích chunk làm câu trả lời**.
5. Filter `domain`/`kind` qua `wiki_list`.
6. Cite nguồn: `[[wiki/<domain>/source/...]]` hoặc URL từ `sources:`.
7. Câu trả lời hay (synthesis, comparison) → file ngược thành page mới (compounding).
8. Retrieval có vẻ kém? `llm-wiki eval --compare` (đọc `eval/golden.toml`) — dùng số liệu, đừng đoán.

## Wikilink format

- **Full path only**: `[[wiki/<domain>/<kind>/<slug>]]`.
- **NO markdown wrapping**: `[text]([[path]])` breaks Obsidian render.
- Alias: `[[path|Custom Text]]`.

## Lint / Review / Consolidate

```bash
llm-wiki lint          # deterministic checks + findings
llm-wiki lint --fix    # xoá dangling rows + thêm index entries (additive)
llm-wiki reindex       # tăng dần theo content-hash (--check dry-run, --full rebuild)
llm-wiki eval --compare  # đo retrieval: P@k/R@k/MRR cho 3 profile (read-only)
```

Lint (tất định): orphan, broken-wikilink, missing-file (CRITICAL), missing-frontmatter, status-vocab, timestamp-format, footnote-sources-match, stale-after-passed, missing-index-entry, pin-orphan, `sources-no-local-path`, `body-no-raw-inbox-wikilink`, dense-bullet/indent-depth/banned-terms (advisory).

Review (sinh sinh, skill `llm-wiki-review` / `wiki-project-review`): contradiction, stale claim, stale code reference (project), khái niệm thiếu, trust gap, pin conflict → gaps vào `wiki/alerts/` (`kind: alert, status: open`); không nêu lại 2 lần liên tiếp → tự đóng. Cadence `[review].interval_days` (watch in `[review] due`).

Consolidate (skill `llm-wiki-consolidate` / `wiki-project-consolidate`): gộp log/mẩu rải rác → concept canonical; additive; distill-verify (citation không co); trùng → `superseded` + `x_supersedes`.

Trust tier: page có `generated: {by, at}`; human duyệt = `llm-wiki verify <path> --by <id>` (set `verified`, cả personal + project). AI KHÔNG tự set `verified`; đổi judgment → `--unverify`.

## MCP tools — centralized server (`llm-wiki-base-mcp`)

Centralized MCP server (1 entry trong Claude/OpenCode/Zed config) phục vụ **tất cả**
wikis qua `~/.llm-wiki-base/registry.toml`. Mỗi tool có param `wiki=` tùy chọn:

- `wiki=""` (rỗng) → **cross-wiki search** (tất cả wikis, kết quả gán `wiki` field).
- `wiki="<name>"` → target wiki cụ thể.

Write tools (wiki_submit, wiki_propose_edit) **bắt buộc** chỉ định `wiki` —
human phải chỉ định wiki để contribute, MCP không tự chọn.

| Tool | Vai trò |
|---|---|
| `wiki_search(query, top_k, wiki="")` | Union retrieval (BM25 page ∪ BM25 chunk ∪ vector chunk) + RRF. Kết quả có `matched_by` + `rank`. `wiki=""` → all wikis |
| `semantic_search(query, top_k, wiki="")` | Chunk-level vector thô (cần RAG index) — chỉ để dò concept |
| `wiki_read(path, wiki="")` | Đọc file. `wiki=""` → tìm trong all wikis |
| `wiki_list(domain, kind, category, wiki="")` | List pages, filter theo domain/kind |
| `list_raw_source(subdir, wiki="")` | List raw sources |
| `read_raw_source(name, subdir, wiki="")` | Đọc raw source để cite |
| `wiki_submit(title, content, wiki, domain, source)` | **Bắt buộc `wiki`**: ghi vào `raw/inbox/` |
| `wiki_propose_edit(path, content, wiki)` | **Bắt buộc `wiki`**: staging → `.proposals/` |
| `wiki_lint(wiki="")` | Health-check. `wiki=""` → lint all wikis |

Resources: `registry://wikis` (list wikis), `wiki://<name>/index`, `wiki://<name>/log`.

**MCP KHÔNG ingest.** MCP chỉ được phép research (search/read/lint) + contribute
vào wiki do human chỉ định (inbox/proposals). Ingest pipeline (tạo/update `wiki/` pages)
là maintainer-only: `llm-wiki ingest` (CLI) hoặc `llm-wiki-ingest` skill.

## An toàn

- **AI proposes, human decides.** Re-derivable writes (index, log) → tự làm. Asserting fact → `wiki_propose_edit` staging.
- **Contradiction = report human**, không materialize edge.
- **Provenance bắt buộc.** Mọi claim có `[[wiki page]]` trong body hoặc URL trong `sources:`.
- **Raw local cache (gitignored).** User có thể xoá tùy ý — provenance nằm trong `sources:` field (URL gốc). Pin source quan trọng: `git add -f raw/<file>`.

## Embedding & retrieval config

Default on-device (no API): `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, đa ngôn ngữ VN/Nhật/Anh).

**Behavior config nằm ở `.llm-wiki.toml`** (wiki root, commit):
```toml
[retrieval]
fusion = "rrf"              # "weighted" = hành vi cũ (rollback + baseline A-B)
chunk_bm25 = true           # kênh BM25 trên semantic chunks
vector = false              # BM25-only mặc định; BẬT sau khi `llm-wiki eval --compare` cho thấy khá hơn
rerank = "llm"              # skill layer rerank; "off" = dùng nguyên thứ tự RRF
chunk_tokens = 512
top_k_bm25 = 20             # ứng viên mỗi kênh text
top_k_vector = 20           # ứng viên kênh vector
top_n_final = 8             # kết quả cuối + budget đọc của skill
relax_recall = true         # giữ nguyên → AND sanitize → OR

[retrieval.weights]         # RRF chỉ nhạy tỉ số
bm25_page = 1.0
bm25_chunk = 1.0
vector = 1.0

[retrieval.index]
embed_model = ""            # rỗng = builtin default

[eval]
k = 8                       # cutoff của `llm-wiki eval`
```

Env override (ưu tiên cao hơn TOML):
- `WIKI_EMBED_MODEL` — model name.
- `WIKI_EMBED_DIM` — vector dim (default 384, phải match model).
- `WIKI_FUSION` (`rrf`|`weighted`), `WIKI_CHUNK_BM25` (`0`/`false` để tắt).
- `WIKI_BM25_WEIGHT`, `WIKI_VEC_WEIGHT` — chỉ chi phối khi `fusion = "weighted"` (RRF seed weight từ đây nhưng chỉ nhạy tỉ số).
- `WIKI_DB` — SQLite path (default `<WIKI_ROOT>/wiki/.wiki.db`).

XEM EFFECTIVE CONFIG: `llm-wiki config show`. Đổi `embed_model`/`chunk_tokens`/`vector`/`fusion` → chạy `llm-wiki reindex --full`.

**Nâng cấp wiki cũ**: `chunks_fts` là bảng mới → incremental reindex BỎ QUA page không đổi hash, nên phải `llm-wiki reindex --full` một lần, nếu không kênh `bm25_chunk` im lặng trống (search vẫn chạy, chỉ là thiếu một kênh).
