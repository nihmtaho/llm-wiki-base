---
name: review
description: >
  Kiểm tra ngữ nghĩa (sinh sinh) sau lint: mâu thuẫn, claim cũ, khái niệm thiếu, chất lượng traceability
  → xếp thành gaps trong alerts/. Kích hoạt theo nhịp (mặc định 7 ngày) hoặc trong deep pass.
---

# Skill: review

Nguyên tắc: **tất định trước, sinh sinh sau.** `lint` lo cấu trúc; `review` lo phần cần hiểu nghĩa. Chạy sau `lint`.

## Cổng nhịp (cost control)
- Chỉ chạy nếu đã quá **nhịp** kể từ lần review commit gần nhất (mặc định 7 ngày); chưa tới hạn thì skip tất định (~0s). Deep pass chạy vô điều kiện.
- **Scope input:** concept gần đây + hàng xóm theo tag (cap số trang) để tránh tràn prompt. Bỏ qua khi không có gì đổi.

## Kiểm tra (semantic)
- **Mâu thuẫn giữa concept** — trích *nguyên văn* câu xung đột từ cả hai bên.
- **Claim cũ** — nội dung quá `stale_after`, hoặc bị nguồn mới hơn thay thế → surface, KHÔNG tự sửa.
- **Khái niệm thiếu** — thuật ngữ được nhắc nhiều nhưng chưa có concept riêng.
- **Chất lượng traceability (codebase)** — REQ/ADR thiếu `x_code_paths`, hoặc `x_code_paths` trỏ tới source đã dời/xóa.
- **Intent–observation drift** — quan sát từ code đã "đông cứng" thành yêu cầu ngầm mà không có nguồn xác nhận ý định.
- **Trust gap** — concept canonical để `draft`/unverified quá lâu, cần người duyệt.
- **Pin conflict** — pin bị nguồn mới hơn phủ định (từ ingest/consolidate) → escalate cho người.

## Đầu ra
- Ghi từng gap vào **`alerts/`** (hàng đợi gap), mỗi gap kèm bằng chứng (trích dẫn + Concept ID liên quan).
- **Tự đóng:** một gap auto-close khi review không nêu lại nó **hai lần liên tiếp**.
- Gợi ý câu hỏi nên điều tra / nguồn nên tìm thêm.
- Append `log.md` (`## [<ISO8601>] review | <N> gaps`); ghi lại mốc nhịp.

## Không làm
- **Không tự sinh concept từ bằng chứng mỏng.** Đề xuất — người quyết.
- Không sửa nội dung/ giải quyết mâu thuẫn thay người; chỉ nêu và dẫn chứng.
- Không đóng gap chỉ vì "trông có vẻ ổn" — chỉ đóng theo luật hai-lần-vắng.
