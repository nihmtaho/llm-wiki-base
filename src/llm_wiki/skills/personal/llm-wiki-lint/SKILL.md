---
name: llm-wiki-lint
description: Health-check LLM wiki — phần TẤT ĐỊNH: orphan, broken link, frontmatter, timestamp, footnote↔sources, index sync, pins orphan, layout. Mâu thuẫn/stale claim là việc của skill llm-wiki-review. Dùng định kỳ hoặc khi human yêu cầu.
---

# LLM Wiki — Lint

Nguyên tắc: **tất định trước, sinh sinh sau.** Skill này chỉ lo phần tất định (cấu trúc); semantic (mâu thuẫn, stale claim, khái niệm thiếu) là việc của skill `llm-wiki-review`.

Schema: `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào
Định kỳ (watch chạy mỗi `WATCH_LINT_SEC`) hoặc human bảo "lint wiki".

## Quy trình
1. Chạy `llm-wiki lint` từ trong `<wiki_root>`:
   ```bash
   llm-wiki lint
   ```
   Trả `page_count`, `orphans`, `missing_file`, `findings` (mỗi finding có tên check).
2. Xử lý từng loại finding:
   - **broken-wikilink**: `[[target]]` trỏ file không tồn tại → sửa path hoặc tạo page.
   - **missing-frontmatter**: page thiếu frontmatter / thiếu `title`/`domain`/`kind` → bổ sung (infer từ path).
   - **status-vocab**: `status`/`confidence` ngoài vocab → sửa (vocab xem `_schema.md`, gồm `planned`/`deprecated`/`superseded`).
   - **timestamp-format**: `updated` sai `YYYY-MM-DD`, `stale_after`/`verified.at`/`generated.at` sai ISO-8601 → sửa format.
   - **stale-after-passed**: `stale_after` quá hạn → report human, KHÔNG tự đổi status.
   - **footnote-sources-match**: `[^id]` không khớp `sources[].id` → sửa citation hoặc sources.
   - **missing-index-entry** / **domain-missing-index**: chạy `llm-wiki lint --fix` — tự thêm entry còn thiếu (additive) + tạo index.md cho domain thiếu.
   - **pin-orphan**: pin trong `wiki/pins.yml` mất concept/anchor → report human, KHÔNG tự xoá pin.
   - **orphan** (page không có inbound `[[link]]`): tìm page liên quan để link tới, hoặc ghi nhận intentional.
   - **missing_file**: page trong DB nhưng thiếu file trên disk → `llm-wiki lint --fix` (xoá dangling rows).
   - **`sources-no-local-path`** / **body-no-raw-inbox-wikilink**: drop `raw/inbox/` path refs.
   - **dense-bullet / indent-depth / banned-terms**: advisory — sửa khi chạm page đó.
3. **Sync index (DB + RAG)** — đảm bảo search DB + RAG đồng bộ với wiki:
   ```bash
   llm-wiki reindex
   ```
   Tăng dần theo content-hash. `reindex --check` dry-run; `--full` khi config đổi.
4. **Chuyển semantic cho review**: mâu thuẫn, stale claim vs source mới, khái niệm thiếu, trust gap → chạy skill `llm-wiki-review` (cadence `[review].interval_days` trong `.llm-wiki.toml`). KHÔNG xử lý semantic ở đây.

## MCP tools
- `wiki_lint` · `wiki_list` · `wiki_read`.

## An toàn
- Lint chỉ báo cáo + auto-fix re-derivable (index entries, dangling DB rows, format). 
- Quyết định semantic (contradiction, stale) thuộc human qua review skill.
- Không xoá page kể cả khi orphan — người quyết định. Không xoá pin.
