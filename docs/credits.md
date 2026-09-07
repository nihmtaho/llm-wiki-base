# Credits & Provenance

Các quy tắc trong template này được tổng hợp từ nhiều nguồn. Ghi nhận ở đây để truy nguyên khi cần giải thích rule hoặc extend schema.

## Quy tắc schema

### Copied state drift
- **Nguồn:** WadeGIMPBC thread.
- **Rule:** Wiki page KHÔNG chứa value move-able (SHA, line count, mtime, count tuyệt đối, local path). Nếu value có thể đổi khi underlying data đổi, nó thuộc về frontmatter (mtime) hoặc tooling (read live). Cite value chỉ khi claim về quá khứ (history) hoặc value phụ thuộc downstream đã nêu tên.
- **Áp dụng:** rule `sources-no-local-path` (không cite `raw/inbox/...` trong `sources:`; `raw/` ngoài inbox cho phép), rule `body-no-raw-inbox-wikilink` (chỉ flag inline `[[raw/inbox/...]]`).

### Human pins
- **Nguồn:** huachen-wang comment.
- **Rule:** Page có thể mang block `pins:` trong frontmatter để con người pin 1 claim cụ thể. Agent re-check pins sau mỗi ingest: còn thoả mãn → giữ, bị supersede → báo human, anchor mất → flag orphan.

## Tech stack & model

- **Embedding:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, đa ngôn ngữ). Run on-device qua `fastembed` — không gọi API ngoài.
- **Search:** SQLite FTS5 (2 bảng: `pages_fts` page-level + `chunks_fts` chunk-level) + numpy cosine trên chunk vectors. 3 kênh xếp hạng độc lập, gộp bằng **RRF trên hạng** (`[retrieval].fusion = "rrf"`), vì `bm25()` và cosine khác thang hoàn toàn. Chế độ cũ `fusion = "weighted"` (cộng thẳng `WIKI_BM25_WEIGHT`/`WIKI_VEC_WEIGHT`) vẫn còn để rollback và để eval A-B.
- **Rerank:** không có model riêng — là bước LLM trong skill query/research (`[retrieval].rerank = "llm"`).
- **Đo lường:** `llm-wiki-base eval` (P@k / R@k / MRR trên `eval/golden.toml`) — quyết định bật vector bằng số, không bằng cảm giác.
- **Web extract:** `trafilatura`. PDF: `pymupdf`. YouTube: yt-dlp / youtube-transcript-api.
- **MCP:** `mcp` Python SDK, stdio transport.

## Naming convention

- Domain = kebab-case, lowercase, ASCII-safe.
- Wiki page path: `wiki/<domain>/<kind>/<slug>.md`.
- Wikilink: `[[wiki/<domain>/<kind>/<slug>]]` (full path, không dùng markdown-wrapped).

## Contributing rule

Template repo (`llm-wiki-base/`) chỉ chứa **generic schema + tooling + skills**. KHÔNG push content thuộc project cụ thể (Expo, GoxViet, JRE, ...) lên đây — đó là content của fork/instance.
