---
name: wiki-project-review
description: Kiểm tra ngữ nghĩa (sinh sinh) project-wiki sau lint — mâu thuẫn, stale claim, stale code reference, khái niệm thiếu, trust gap, pin conflict → ghi gaps vào wiki/alerts/. Cadence-gated qua [review].interval_days. Companion của wiki-project-lint.
---

# Wiki Project — Review

Nguyên tắc: **tất định trước, sinh sinh sau.** `wiki-project-lint` lo cấu trúc (chạy trước); skill này lo phần cần hiểu nghĩa, kể cả verdict stale-vs-code. Chạy sau lint.

## Cổng nhịp (cost control)
- Đọc watermark `wiki/.review_state.json` (`last_run`). Chỉ chạy full nếu quá `[review].interval_days` (`.llm-wiki.toml`); chưa tới hạn → skip, báo "review not due".
- Deep pass (human bảo rõ "deep review") chạy vô điều kiện.
- **Scope input**: entity/concept/source gần đây + hàng xóm theo tag — cap `[review].max_pages`; vượt → chỉ recent + tag-neighbor.

## Quy trình
1. Chọn ứng viên theo scope. Đọc pages + `wiki/pins.yml` + gaps `open` trong `wiki/alerts/`.
2. **Kiểm tra semantic** (mỗi gap kèm BẰNG CHỨNG: trích nguyên văn + Concept ID):
   - **Mâu thuẫn giữa concept** — trích nguyên văn cả hai bên.
   - **Mâu thuẫn wiki ↔ code** — wiki claim trái với code hiện tại.
   - **Stale code reference** — với mỗi code path được reference trong entity/concept: `grep`/`find` confirm trong codebase; path mất → flag stale, đề xuất update, KHÔNG tự sửa.
   - **Claim cũ** — quá `stale_after` hoặc bị source mới hơn thay thế → surface.
   - **Khái niệm thiếu** — thuật ngữ nhắc nhiều chưa có concept riêng → đề xuất.
   - **Trust gap** — concept canonical để `draft`/unverified lâu → gợi ý human duyệt qua `llm-wiki verify <path> --by <id>` (cùng cơ chế personal + project).
   - **Pin conflict** — pin `active` bị source mới phủ định → escalate human.
3. **Ghi gap** vào `wiki/alerts/<slug>.md`: frontmatter `domain: alerts, kind: alert, status: open, last_seen: <date>`; body = bằng chứng + gợi ý. Gap trùng chủ đề → update `last_seen`.
4. **Tự đóng**: gap không nêu lại 2 lần liên tiếp → `status: closed`. KHÔNG đóng vì "trông có vẻ ổn".
5. **Cập nhật**: watermark `wiki/.review_state.json`; append `wiki/log.md` (`## [<ISO8601>] review | <N> gaps`).
6. Báo cáo: gaps mới / mở / tự đóng + phần cần human quyết.

## Không làm
- Không tự sinh concept từ bằng chứng mỏng — đề xuất, người quyết.
- Không sửa nội dung / code path stale thay người — chỉ nêu và dẫn chứng.
- Không set/clear `verified` — `llm-wiki verify` là lệnh của human.
- Stale check vs code là heuristic (case sensitivity, glob, monorepo paths) — confirm với human.
