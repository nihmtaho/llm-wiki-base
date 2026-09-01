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
6. Insert vào `wiki/log.md` (reverse-chronological). Format: `## [YYYY-MM-DD HH:MM:SS] <op> | <title>` với `op ∈ ingest|wiki_lint|migrate|fix`. Body bullets chỉ viết action thực sự có.
7. Index DB: `.venv/bin/python tools/ingest.py <path>` (KHÔNG qua MCP).
8. Move source: cả URL + no-URL đều → `raw/` (local cache, có thể xoá). Watch daemon tự động.

## Query

- Hybrid: MCP `wiki_search(query, top_k=8)`. Filter `domain`/`kind` qua `wiki_list`.
- Semantic chunk: `semantic_search(query, top_k=6)`. Cần build `rag/index.py` trước.
- Cite nguồn: `[[wiki/<domain>/source/...]]` hoặc URL từ `sources:`.
- Câu trả lời hay (synthesis, comparison) → file ngược thành page mới (compounding).

## Wikilink format

- **Full path only**: `[[wiki/<domain>/<kind>/<slug>]]`.
- **NO markdown wrapping**: `[text]([[path]])` breaks Obsidian render.
- Alias: `[[path|Custom Text]]`.

## Lint

```bash
PYTHONPATH=tools .venv/bin/python -c "import db,lint; print(lint.lint(db.get_conn()))"
```

Tìm:
- Orphan pages (không có inbound link).
- Broken `[[wikilinks]]` (target không tồn tại).
- Missing file trên disk (CRITICAL — search trả row nhưng file gone).
- `sources:` chứa `raw/inbox/...` path (rule `sources-no-local-path`). `raw/` (ngoài inbox) cho phép.
- Body inline `[[raw/inbox/...]]` (rule `body-no-raw-inbox-wikilink`). `[[raw/...]]` (ngoài inbox) cho phép.
- Frontmatter thiếu `domain`/`kind`.
- Domain mới chưa có `index.md`.

Contradiction KHÔNG tự resolve — report cho human, không materialize thành edge.

## MCP tools (9 tools)

| Tool | Vai trò |
|---|---|
| `wiki_search(query, top_k)` | Hybrid BM25 + vector trên wiki + raw |
| `semantic_search(query, top_k)` | Chunk-level vector (cần `rag/index.py`) |
| `wiki_read(path)` | Đọc 1 file (rel to WIKI_ROOT) |
| `wiki_list(domain, kind)` | Liệt kê pages, filter theo domain/kind |
| `list_raw_source(subdir)` | Liệt kê filename trong `raw/<subdir>/` |
| `read_raw_source(name, subdir)` | Đọc raw source để cite provenance |
| `wiki_submit(title, content, domain, source)` | **Ghi vào `raw/inbox/`** (KHÔNG wiki) |
| `wiki_propose_edit(path, content)` | Staging vào `wiki/.proposals/`, chờ human sign-off |
| `wiki_lint()` | Health-check wiki |

**MCP KHÔNG BAO GIỜ ghi trực tiếp vào `wiki/`.** Ingest là maintainer-only.

## An toàn

- **AI proposes, human decides.** Re-derivable writes (index, log) → tự làm. Asserting fact → `wiki_propose_edit` staging.
- **Contradiction = report human**, không materialize edge.
- **Provenance bắt buộc.** Mọi claim có `[[wiki page]]` trong body hoặc URL trong `sources:`.
- **Raw local cache (gitignored).** User có thể xoá tùy ý — provenance nằm trong `sources:` field (URL gốc). Pin source quan trọng: `git add -f raw/<file>`.

## Embedding

Default on-device (no API): `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, đa ngôn ngữ VN/Nhật/Anh).

Env override:
- `WIKI_EMBED_MODEL` — model name (default trên).
- `WIKI_EMBED_DIM` — vector dim (default 384, phải match model).
- `WIKI_BM25_WEIGHT`, `WIKI_VEC_WEIGHT` — hybrid search tuning (default 0.5/0.5).
- `WIKI_DB` — SQLite path (default `<WIKI_ROOT>/wiki/.wiki.db`).

Đổi model → phải rebuild `rag/.rag_index/`.
