---
name: consolidate
description: >
  Gộp log-layer và các mẩu rải rác thành concept canonical theo khái niệm; merge tại chỗ, additive,
  tái grounding từ raw. Kích hoạt định kỳ hoặc khi người dùng nói "consolidate", "gộp topic".
---

# Skill: consolidate

Mục tiêu: biến các entry theo thời gian thành tri thức canonical theo khái niệm, mà không mất bằng chứng và không tự bồi hallucination.

## Nguyên tắc bất di
- **Chỉ raw → concept.** Không tái sinh concept từ concept khác. Mọi claim phải trace về `sources[]` trỏ vào `raw/`.
- **Additive merge.** Dòng đang có là bất biến; merge chỉ *thêm*. Không viết lại/ xóa nội dung cũ trừ khi deprecate có chủ đích.
- **Single source per fact.** Nếu hai concept giữ cùng một sự thật → chọn bản canonical, bản kia set `status: deprecated` + `x_supersedes: <canonical-id>`, để lại con trỏ.

## Quy trình
1. Đọc `SCHEMA.md` (profile, quy ước). Xác định watermark consolidate lần trước (tránh xử lý lại).
2. **Chọn ứng viên:** entry mới trong `log.md` kể từ watermark + các topic có thông tin rải rác across concept.
3. Với mỗi topic → xác định **concept canonical đích**.
4. **Tái grounding:** thu thập material từ `raw/` (không từ concept khác); mỗi claim gộp vào phải có footnote `sources[].id`.
5. **Merge tại chỗ (additive)** vào concept đích. Giữ body có cấu trúc; wikilink theo Concept ID.
6. **Tôn trọng pins:** đọc `pins.yml`; sau merge, re-check từng pin `active`. Còn đúng → giữ; bị nguồn mới hơn phủ định → đẩy cho người (`alerts/`), KHÔNG revert; section mất → orphan.
7. **VERIFY added claims (distill-verify):** tập citation của concept sau merge **không được co lại** so với trước. Mỗi claim mới phải dẫn nguồn. Nếu nội dung đổi mang tính judgment → clear `verified` phần đó (hạ về unverified) để chờ người duyệt lại.
8. **Cập nhật:** frontmatter `generated: {by, at}` mới; `index.md` mô tả lại; deprecate bản trùng; append `log.md` (`## [<ISO8601>] consolidate | <topic>`); đẩy watermark.
9. **Báo cáo:** concept nào được gộp, bản nào deprecate, citation trước/sau, phần nào cần người duyệt.

## Không làm
- Không co/ mất citation. Không xóa nội dung con người. Không nâng `verified` thay người.
