---
name: wiki-project-lint
description: Health-check TẤT ĐỊNH project-wiki — orphan, broken link, missing file, frontmatter, timestamp, footnote↔sources, index sync, pins orphan. Stale code reference + contradiction là việc của wiki-project-review. Companion của wiki-project-research + wiki-project-ingest.
---

# Wiki Project — Lint

Nguyên tắc: **tất định trước, sinh sinh sau.** Skill này lo cấu trúc; semantic (mâu thuẫn, stale claim, stale code reference verdict) là việc của skill `wiki-project-review`.

Schema: `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào

Định kỳ (watch chạy mỗi `WATCH_LINT_SEC`) hoặc human bảo "lint wiki".

## Quy trình

1. Chạy `llm-wiki lint` từ trong `<wiki_root>` (vd `<project>/project-wiki/`):
   ```bash
   llm-wiki lint
   ```
   Trả `page_count`, `orphans`, `missing_file`, `findings` (mỗi finding có tên check).
2. Xử lý từng loại finding:
   - **orphan** (page không có inbound `[[link]]`): tìm page liên quan để link tới, hoặc ghi nhận intentional.
   - **missing_file**: page trong DB nhưng thiếu file trên disk → `llm-wiki lint --fix` (xoá dangling rows).
   - **broken-wikilink**: `[[target]]` trỏ file không tồn tại → sửa.
   - **missing-index-entry** / **domain-missing-index**: `llm-wiki lint --fix` — tự thêm entry (additive) + tạo index.md.
   - **missing-frontmatter** / **status-vocab** / **timestamp-format**: sửa frontmatter theo `_schema.md` (vocab gồm `planned`/`deprecated`/`superseded`).
   - **stale-after-passed**: `stale_after` quá hạn → report human, KHÔNG tự đổi status.
   - **footnote-sources-match**: `[^id]` không khớp `sources[].id` → sửa citation hoặc sources.
   - **`sources-no-local-path`** / **body-no-raw-inbox-wikilink**: drop `raw/inbox/` refs.
   - **pin-orphan**: pin trong `wiki/pins.yml` mất concept/anchor → report human, KHÔNG tự xoá pin.
   - **dense-bullet / indent-depth / banned-terms**: advisory.
3. **Code path thu thập** (project-specific, input cho review):
   - Extract code paths/filenames được reference trong entity + concept pages → chuyển danh sách cho `wiki-project-review` verdict stale (grep/find confirm). KHÔNG tự kết luận + tự sửa ở đây.
4. **Sync index (DB + RAG)**:
   ```bash
   llm-wiki reindex
   ```
   Tăng dần theo content-hash; `--check` dry-run; `--full` khi config đổi.
5. **Chuyển semantic cho review**: contradiction, stale claim vs source mới, stale code path verdict → skill `wiki-project-review` (cadence `[review].interval_days`).

## MCP tools

- `wiki_lint` · `wiki_list` · `wiki_read` · `wiki_search`.

## An toàn

- Lint chỉ báo cáo + auto-fix re-derivable (index entries, dangling rows, format).
- Quyết định semantic (contradiction, stale, code ref stale) thuộc human qua review skill.
- Không xoá page kể cả khi orphan — người quyết định. Không xoá pin.
- Stale check vs code chỉ là heuristic — confirm với human trước khi update.
