---
name: wiki-project-lint
description: Health-check project-wiki — tìm orphan page, broken link, missing file, stale code reference, frontmatter thiếu domain/kind, stale claim. Contradiction với code báo human. Companion của wiki-project-research + wiki-project-ingest.
---

# Wiki Project — Lint

Schema: `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào

Định kỳ (watch chạy mỗi `WATCH_LINT_SEC`) hoặc human bảo "lint wiki" / "check wiki có stale không".

## Quy trình

1. Chạy `llm-wiki lint` từ trong `<wiki_root>` (vd `<project>/project-wiki/`):
   ```bash
   llm-wiki lint
   ```
   Trả `page_count`, `orphans`, `missing_file`, `findings`.
2. Xử lý:
   - **orphan** (page không có inbound `[[link]]`): tìm page liên quan để link tới, hoặc ghi nhận intentional.
   - **missing_file**: page trong DB nhưng thiếu file trên disk → reconcile (chạy `llm-wiki reindex`).
   - **broken link**: `[[target]]` trỏ sai path → sửa.
   - **missing index entry**: page chưa có trong `<wiki_root>/wiki/<domain>/index.md` hoặc domain mới chưa có row trong `<wiki_root>/wiki/index.md` → thêm.
   - **frontmatter thiếu `domain`/`kind`**: page cũ chỉ có `category: <folder>` → bổ sung `domain` + `kind` mới.
   - **`sources:` chứa local path** (rule `sources-no-local-path`): drop, đặt `[]` hoặc chỉ giữ URL.
   - **Body inline `[[raw/inbox/...]]`** (rule `body-no-raw-inbox-wikilink`): xoá. `[[raw/...]]` (ngoài inbox) cho phép.
3. **Stale check vs code** (project-specific, quan trọng):
   - Lấy tất cả `entity` + `concept` pages, extract code paths/filenames được reference.
   - Với mỗi path: `grep` / `find` xem còn tồn tại trong codebase không.
   - Nếu path không tồn tại → flag stale, đề xuất update.
   - **Không tự sửa** stale claim về code — báo human.
4. **Sync index (DB + RAG)**: đảm bảo `<wiki_root>/wiki/.wiki.db` + `<wiki_root>/rag/.rag_index/` đồng bộ với wiki:
   ```bash
   llm-wiki reindex
   ```
   Idempotent — index `raw/**` + `wiki/**` vào DB + rebuild RAG.
5. **Contradiction** (2 page claim mâu thuẫn, hoặc wiki claim ↔ code mâu thuẫn): đọc kỹ, **report human** kèm trích dẫn. KHÔNG materialize thành edge.
6. **Stale claim vs source mới hơn**: source mới supersede → đánh dấu `status: stale` + `confidence: superseded`, đề xuất update.
7. **Domain coverage**: liệt kê tất cả top-level folder `wiki/*/` (không tính `index.md`, `log.md`, `.proposals/`). Mỗi folder nên có `index.md`.

## MCP tools

- `wiki_lint` · `wiki_list` · `wiki_read` · `wiki_search`.

## An toàn

- Lint chỉ báo cáo. Sửa cross-link/index/frontmatter là re-derivable → agent tự làm.
- Quyết định semantic (contradiction, stale, code ref stale) thuộc human.
- Không xoá page kể cả khi orphan — người quyết định.
- **Stale check vs code chỉ là heuristic** — grep có thể miss (case sensitivity, glob pattern, monorepo paths). Confirm với human trước khi update.
