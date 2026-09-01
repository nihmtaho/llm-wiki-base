---
name: llm-wiki-review
description: Kiểm tra ngữ nghĩa (sinh sinh) sau lint — mâu thuẫn, claim cũ, khái niệm thiếu, trust gap, pin conflict → ghi gaps vào wiki/alerts/. Cadence-gated qua [review].interval_days. Chạy khi human bảo "review wiki" hoặc watch báo due.
---

# LLM Wiki — Review

Nguyên tắc: **tất định trước, sinh sinh sau.** `llm-wiki-lint` lo cấu trúc (chạy trước); skill này lo phần cần hiểu nghĩa. Chạy sau lint.

## Cổng nhịp (cost control)
- Đọc watermark `wiki/.review_state.json` (`last_run`). Chỉ chạy full nếu quá `[review].interval_days` (`.llm-wiki.toml`); chưa tới hạn → skip (~0s), báo "review not due".
- Deep pass (human bảo rõ "deep review") chạy vô điều kiện.
- **Scope input**: concept/source gần đây + hàng xóm theo tag — cap `[review].max_pages` (default 80); vượt → chỉ recent + tag-neighbor. Bỏ qua khi không có gì đổi từ lần trước.

## Quy trình
1. Chọn ứng viên theo scope trên. Đọc pages + `wiki/pins.yml` + gaps `status: open` trong `wiki/alerts/`.
2. **Kiểm tra semantic** (mỗi gap kèm BẰNG CHỨNG: trích nguyên văn + Concept ID liên quan):
   - **Mâu thuẫn giữa concept** — trích nguyên văn câu xung đột từ cả hai bên.
   - **Claim cũ** — nội dung quá `stale_after`, hoặc bị source mới hơn thay thế → surface, KHÔNG tự sửa.
   - **Khái niệm thiếu** — thuật ngữ được nhắc nhiều nhưng chưa có concept riêng → đề xuất (không tự tạo).
   - **Trust gap** — concept canonical để `draft`/unverified quá lâu → gợi ý human duyệt qua `llm-wiki verify <path> --by <id>` (cả personal + project cùng cơ chế).
   - **Pin conflict** — pin `active` bị source mới hơn phủ định (từ ingest/consolidate) → escalate human.
3. **Ghi gap** vào `wiki/alerts/<slug>.md`:
   - Frontmatter: `title`, `domain: alerts`, `kind: alert`, `status: open`, `last_seen: <YYYY-MM-DD>`, `sources` trỏ các concept liên quan.
   - Body: bằng chứng (trích nguyên văn + link `[[...]]`) + gợi ý điều tra/nguồn nên tìm thêm.
   - Gap đã có sẵn (cùng chủ đề) → update `last_seen` hôm nay, không tạo trùng.
4. **Tự đóng gap**: gap `open` mà lần review này KHÔNG nêu lại và `last_seen` cũ hơn lần trước 1 nhịp (2 lần vắng liên tiếp) → `status: closed`. KHÔNG đóng vì "trông có vẻ ổn".
5. **Cập nhật**: watermark `wiki/.review_state.json` `{"last_run": "<ISO>", "gaps": <số>}`; append `wiki/log.md` (`## [<ISO8601>] review | <N> gaps`).
6. Báo cáo: gaps mới / còn mở / tự đóng, và phần nào cần human quyết.

## Không làm
- Không tự sinh concept từ bằng chứng mỏng — đề xuất, người quyết.
- Không sửa nội dung / giải quyết mâu thuẫn thay người — chỉ nêu và dẫn chứng.
- Không set/clear `verified` — `llm-wiki verify` là lệnh của human.
- Không xóa gap file — chỉ đóng bằng `status: closed`.
