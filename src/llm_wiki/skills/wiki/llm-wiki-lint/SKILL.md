---
name: llm-wiki-lint
description: >
  Health-check PHẦN TẤT ĐỊNH của wiki — orphan, broken wikilink, frontmatter, timestamp,
  footnote↔sources, index sync, pins orphan, layout. Mâu thuẫn / claim cũ / stale code
  reference là việc của `llm-wiki-review`. Dùng định kỳ hoặc khi human bảo "lint wiki".
---

# LLM Wiki — Lint

Nguyên tắc: **tất định trước, sinh sinh sau.** Skill này chỉ lo cấu trúc; semantic (mâu thuẫn, claim cũ, khái niệm thiếu, code path không còn) là việc của `llm-wiki-review`.

Schema: `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào

Định kỳ (`llm-wiki watch` tự chạy mỗi `WATCH_LINT_SEC`) hoặc human bảo "lint wiki".

## Quy trình

1. Chạy từ trong `<wiki_root>`:
   ```bash
   llm-wiki lint
   ```
   Trả `page_count`, `orphans`, `missing_file`, `findings` (mỗi finding có tên check).
2. Xử lý từng loại finding:
   - **broken-wikilink**: `[[target]]` trỏ file không tồn tại → sửa path hoặc tạo page.
   - **missing-frontmatter**: thiếu frontmatter / thiếu `title`/`domain`/`kind` → bổ sung (infer từ path).
   - **status-vocab**: `status`/`confidence` ngoài vocab → sửa (vocab xem `_schema.md`, gồm `planned`/`deprecated`/`superseded`).
   - **timestamp-format**: `updated` sai `YYYY-MM-DD`, `stale_after`/`verified.at`/`generated.at` sai ISO-8601 có offset → sửa format.
   - **stale-after-passed**: `stale_after` quá hạn → report human, **KHÔNG tự đổi status**.
   - **footnote-sources-match**: `[^id]` không khớp `sources[].id` (và ngược lại) → sửa citation hoặc sources.
   - **missing-index-entry** / **domain-missing-index**: `llm-wiki lint --fix` — tự thêm entry còn thiếu (additive) + tạo `index.md` cho domain thiếu.
   - **pin-orphan**: pin trong `wiki/pins.yml` mất concept/anchor → report human, **KHÔNG tự xoá pin**.
   - **orphan** (page không có inbound `[[link]]`): tìm page liên quan để link tới, hoặc ghi nhận intentional.
   - **missing_file**: page trong DB nhưng thiếu file trên đĩa → `llm-wiki lint --fix` (xoá dangling rows).
   - **`sources-no-local-path`** / **body-no-raw-inbox-wikilink**: bỏ reference tới `raw/inbox/`.
   - **dense-bullet / indent-depth / banned-terms**: advisory — sửa khi chạm page đó (`[lint]` trong `.llm-wiki.toml`).
3. **[codebase] Thu thập code path** (đầu vào cho review, KHÔNG kết luận ở đây):
   - Extract mọi code path / filename được reference trong `entity/` + `concept/` pages.
   - `grep`/`find`/`ls` xem path còn tồn tại không → lập danh sách {path, page nhắc tới, còn/mất}.
   - Danh sách này chuyển cho `llm-wiki-review` để ra verdict stale. **Không tự sửa page trong lint** — đây là heuristic, không phải sự thật.
4. **Sync index (DB + chunk index)**:
   ```bash
   llm-wiki reindex
   ```
   Tăng dần theo content-hash. `--check` = dry-run (báo sẽ index/xoá gì + config drift + trạng thái chunk index); `--full` khi config đổi. Chi tiết: skill `llm-wiki-reindex`.
5. **Chuyển semantic cho review**: mâu thuẫn, claim cũ vs source mới, khái niệm thiếu, trust gap, **[codebase]** stale code reference verdict → skill `llm-wiki-review` (cadence `[review].interval_days`). **Không xử lý semantic ở đây.**

## MCP tools

`wiki_lint(wiki)` · `wiki_list(domain, kind, wiki)` · `wiki_read(path, wiki)` · `wiki_search(query, wiki)`.

## An toàn

- Lint chỉ báo cáo + auto-fix thứ **re-derivable**: index entries, dangling DB rows, format.
- Quyết định semantic thuộc human (qua review skill).
- **Không xoá page** kể cả khi orphan — người quyết định. Không xoá pin. Không đụng `wiki/.proposals/` (đó là việc của `llm-wiki proposals`).
- **[codebase]** Stale check với code chỉ là heuristic — confirm với human trước khi update page.
