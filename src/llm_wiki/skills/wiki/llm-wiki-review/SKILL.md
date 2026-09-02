---
name: llm-wiki-review
description: >
  Kiểm tra ngữ nghĩa (sinh sinh) SAU lint — mâu thuẫn giữa concept, claim cũ, khái niệm
  thiếu, trust gap, pin conflict, [codebase] stale code reference + intent/observation
  drift → ghi gaps vào wiki/alerts/. Cadence-gated qua [review].interval_days. Chạy khi
  human bảo "review wiki" hoặc watch báo due.
---

# LLM Wiki — Review

Nguyên tắc: **tất định trước, sinh sinh sau.** `llm-wiki-lint` lo cấu trúc (chạy TRƯỚC); skill này lo phần cần hiểu nghĩa.

## Cổng nhịp (cost control)

- Đọc watermark `wiki/.review_state.json` (`last_run`). Chỉ chạy full nếu đã quá `[review].interval_days` (`.llm-wiki.toml`); chưa tới hạn → skip tất định (~0s), báo "review not due".
- Deep pass (human nói rõ "deep review") chạy vô điều kiện.
- **Scope input**: page gần đây + hàng xóm theo tag — cap `[review].max_pages` (mặc định 80); vượt → chỉ recent + tag-neighbor. Bỏ qua khi không có gì đổi từ lần trước.
  - **[personal]** scope = `concept/` + `source/`. **[codebase]** scope = `entity/` + `concept/` + `source/`.

## Quy trình

1. Chọn ứng viên theo scope trên. Đọc pages + `wiki/pins.yml` + gaps `status: open` trong `wiki/alerts/` (và danh sách code path do `llm-wiki-lint` bước 3 chuyển sang, nếu profile là codebase).
2. **Kiểm tra semantic** — mỗi gap phải kèm **BẰNG CHỨNG**: trích nguyên văn + Concept ID liên quan.
   - **Mâu thuẫn giữa concept** — trích nguyên văn câu xung đột từ cả hai bên.
   - **[codebase] Mâu thuẫn wiki ↔ code** — page nói X, code làm Y.
   - **[codebase] Stale code reference** — với mỗi code path được reference: `grep`/`find` confirm; path mất/dời → flag stale. **Không tự sửa page.** Stale check chỉ là heuristic → verdict cuối cùng thuộc human.
   - **Claim cũ** — quá `stale_after`, hoặc bị source mới hơn thay thế → surface, không tự sửa.
   - **Khái niệm thiếu** — thuật ngữ nhắc nhiều nhưng chưa có concept riêng → đề xuất, không tự tạo.
   - **[codebase] Intent–observation drift** — quan sát từ code bị "đông cứng" thành yêu cầu ngầm mà không có nguồn xác nhận ý định.
   - **Trust gap** — concept canonical để `draft`/unverified quá lâu → gợi ý human duyệt: `llm-wiki verify <path> --by <id>`.
   - **Pin conflict** — pin `active` bị source mới hơn phủ định (từ ingest/consolidate) → escalate human.
3. **Ghi gap** vào `wiki/alerts/<slug>.md`:
   - Frontmatter: `title`, `domain: alerts`, `kind: alert`, `status: open`, `last_seen: <YYYY-MM-DD>`, `sources` trỏ các concept liên quan.
   - Body: bằng chứng (trích nguyên văn + `[[link]]`) + gợi ý câu hỏi nên điều tra / nguồn nên tìm thêm.
   - Gap đã có (cùng chủ đề) → update `last_seen` hôm nay, không tạo trùng.
4. **Tự đóng gap**: gap `open` mà pass này KHÔNG nêu lại và `last_seen` vắng **hai nhịp liên tiếp** → `status: closed`. KHÔNG đóng vì "trông có vẻ ổn".
5. **Cập nhật**: watermark `wiki/.review_state.json` = `{"last_run": "<ISO>", "gaps": <số>}`; append `wiki/log.md` (`## [<ISO8601>] review | <N> gaps`).
6. Báo cáo: gaps mới / còn mở / tự đóng, và phần nào cần human quyết.

## Không làm

- **Không tự sinh concept từ bằng chứng mỏng** — đề xuất, người quyết.
- Không sửa nội dung / giải quyết mâu thuẫn thay người — chỉ nêu và dẫn chứng.
- Không set/clear `verified` — `llm-wiki verify` là lệnh của human.
- Không xóa file gap — chỉ đóng bằng `status: closed`.
- **[codebase]** Không kết luận stale chỉ vì grep không thấy path (alias, re-export, dynamic import).
