---
name: wiki-project-consolidate
description: Gộp log-layer và các mẩu rải rác thành concept canonical trong project-wiki — merge additive, tái grounding từ raw, distill-verify (citation không co), tôn trọng pins. Kích hoạt định kỳ hoặc khi human nói "consolidate".
---

# Wiki Project — Consolidate

Mục tiêu: biến entry theo thời gian (log.md, source pages trùng) thành tri thức canonical theo khái niệm, không mất bằng chứng, không bồi hallucination.

## Nguyên tắc bất di
- **Chỉ raw → concept.** Không tái sinh concept từ concept khác. Mọi claim gộp vào phải trace về nguồn.
- **Additive merge.** Nội dung đang có là bất biến; merge chỉ *thêm*.
- **Single source per fact.** Trùng → bản lẻ `status: superseded` + `x_supersedes: <canonical-path>`, giữ con trỏ.
- **Pins (`wiki/pins.yml`)**: pin `active` bám section nào → section đó bất biến. Mâu thuẫn → `wiki/alerts/`, KHÔNG revert âm thầm.

## Quy trình
1. Đọc watermark `wiki/.consolidate_state.json` (`last_entry`).
2. **Chọn ứng viên**: entry log.md sau watermark + topic rải rác (human chỉ định thì ưu tiên).
3. Xác định **concept canonical đích** (`wiki/<domain>/concept/<slug>.md`); chưa có → tạo mới (tôn trọng `status: planned` chống fork).
4. **Tái grounding** từ source/raw; mỗi claim có citation `[^id]` khớp `sources[].id`.
5. **Merge additive** vào concept đích; wikilink theo path.
6. **Re-check pins** sau merge; orphan/mâu thuẫn → `wiki/alerts/`.
7. **Distill-verify**: citation set sau merge không co lại (đếm `[^id]` trước/sau).
8. **Trust**: thay đổi judgment → `llm-wiki verify <path> --unverify` (hạ về unverified, chờ human duyệt). KHÔNG tự set `verified`.
9. **Cập nhật**: `generated: {by, at}` mới; index.md; deprecate bản trùng; append log (`## [<ISO8601>] consolidate | <topic>`); đẩy watermark; `llm-wiki reindex` (tăng dần).
10. **Báo cáo**: concept gộp, bản deprecate, citation trước/sau, phần cần human duyệt.

## Không làm
- Không co/mất citation. Không xoá nội dung human. Không nâng `verified` thay người.
- Không xoá file concept — chỉ deprecate + con trỏ.
