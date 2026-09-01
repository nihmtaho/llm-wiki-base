---
name: llm-wiki-lint
description: Health-check LLM wiki — tìm orphan page, broken link, missing index entry, frontmatter thiếu domain/kind, stale claim. Contradiction báo human. Dùng định kỳ hoặc khi human yêu cầu.
---

# LLM Wiki — Lint

Schema: `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào
Định kỳ (watch chạy mỗi `WATCH_LINT_SEC`) hoặc human bảo "lint wiki".

## Quy trình
1. Chạy `llm-wiki lint` từ trong `<wiki_root>`:
   ```bash
   llm-wiki lint
   ```
   Trả `page_count`, `orphans`, `missing_file`, `findings`.
2. Xử lý:
   - **orphan** (page không có inbound `[[link]]`): tìm page liên quan để link tới, hoặc ghi nhận intentional.
   - **missing_file**: page trong DB nhưng thiếu file trên disk → reconcile (chạy `llm-wiki reindex`).
   - **broken link**: `[[target]]` trỏ sai path → sửa.
   - **missing index entry**: page chưa có trong `<wiki_root>/wiki/<domain>/index.md` hoặc domain mới chưa có row trong `<wiki_root>/wiki/index.md` → thêm.
   - **frontmatter thiếu `domain`/`kind`**: page cũ chỉ có `category: <folder>`. Khi sửa, bổ sung `domain` + `kind` mới (infer từ path hoặc detect đúng).
   - **`sources:` chứa local path** (rule `sources-no-local-path`): drop path, đặt `[]` hoặc chỉ giữ URL.
   - **Body inline `[[raw/inbox/...]]`** (rule `body-no-raw-inbox-wikilink`): xoá hoặc chuyển vào `sources:`. `[[raw/...]]` (ngoài inbox) cho phép.
3. **Sync index (DB + RAG)** — đảm bảo search DB (`<wiki_root>/wiki/.wiki.db`) và RAG (`<wiki_root>/rag/.rag_index/`) đồng bộ với wiki:
   ```bash
   llm-wiki reindex
   ```
   Idempotent — index `raw/**` + `wiki/**` vào DB + rebuild RAG.
4. **Contradiction** (2 page claim mâu thuẫn): đọc kỹ, **report human** kèm trích dẫn. Không materialize thành edge trên lời model.
5. **Stale claim**: source mới hơn đã supersede → đánh dấu `status: stale` + `confidence: superseded`, đề xuất update.
6. **Domain coverage**: liệt kê tất cả top-level folder `wiki/*/` (không tính `index.md`, `log.md`, `.proposals/`). Mỗi folder nên có `index.md`. Nếu folder không có `index.md` hoặc có nhưng rỗng → tạo/cập nhật.

## MCP tools
- `wiki_lint` · `wiki_list` · `wiki_read`.

## An toàn
- Lint chỉ báo cáo. Sửa cross-link/index/frontmatter là re-derivable → agent tự làm.
- Quyết định semantic (contradiction, stale) thuộc human.
- Không xoá page kể cả khi orphan — người quyết định.
