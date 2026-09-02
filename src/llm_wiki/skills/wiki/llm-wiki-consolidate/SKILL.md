---
name: llm-wiki-consolidate
description: >
  Gộp log-layer và các mẩu rải rác thành concept canonical — merge tại chỗ, additive,
  tái grounding từ raw, distill-verify (citation không được co lại). Kích hoạt định kỳ
  hoặc khi human nói "consolidate", "gộp topic".
---

# LLM Wiki — Consolidate

Biến entry theo thời gian (`log.md`, source pages trùng lặp) thành tri thức canonical theo khái niệm, mà không mất bằng chứng và không tự bồi hallucination.

## Nguyên tắc bất di

- **Chỉ raw → concept.** Không tái sinh concept từ concept khác. Mọi claim gộp vào phải trace về nguồn (`sources[]` trỏ URL / `raw/` / source page).
- **Additive merge.** Nội dung đang có là bất biến; merge chỉ *thêm*. Không viết lại/xoá nội dung cũ trừ khi deprecate có chủ đích.
- **Single source per fact.** Hai concept giữ cùng một sự thật → chọn bản canonical, bản kia `status: superseded` + `x_supersedes: <canonical-path>`, để lại con trỏ (**không xoá file**).
- **Pins** (`wiki/pins.yml`): pin `active` bám section nào → section đó bất biến. Section mất / pin bị nguồn mới phủ định → đẩy vào `wiki/alerts/`, **không revert âm thầm**.

## Quy trình

1. Đọc watermark `wiki/.consolidate_state.json` (`last_entry` — mốc log lần trước, tránh xử lý lại).
2. **Chọn ứng viên**: entry mới trong `wiki/log.md` kể từ watermark + topic có thông tin rải rác across pages (human chỉ định topic → ưu tiên topic đó).
   - **[codebase]** Ưu tiên topic mà nhiều `entity`/`source` page cùng nhắc một pattern — đó là dấu hiệu concept canonical thiếu.
3. Với mỗi topic → xác định **concept canonical đích** (`wiki/<domain>/concept/<slug>.md`). Chưa có → tạo mới theo schema; tôn trọng `status: planned` chống fork (xem `_schema.md`).
4. **Tái grounding**: thu thập material từ source/raw (**không từ concept khác**); mỗi claim gộp vào phải có citation `[^id]` khớp `sources[].id`.
5. **Merge tại chỗ (additive)** vào concept đích — giữ body có cấu trúc, wikilink theo path.
6. **Re-check pins** sau merge: còn đúng → giữ; bị phủ định → `wiki/alerts/`; section mất → orphan (báo human).
7. **Distill-verify**: tập citation `[^id]` của concept sau merge **không được co lại** so với trước — đếm trước/sau, in ra báo cáo. Mỗi claim mới phải dẫn nguồn.
8. **Trust**: phần nội dung đổi mang tính judgment → `llm-wiki verify <path> --unverify` để hạ `verified` (chờ human duyệt lại). **Không tự set `verified`.**
9. **Cập nhật**: frontmatter `generated: {by, at}` mới; `wiki/<domain>/index.md` mô tả lại nếu cần; deprecate bản trùng (`x_supersedes`); append `wiki/log.md` (`## [<ISO8601>] consolidate | <topic>` — chèn theo thứ tự reverse-chronological, dùng Edit với anchor, không rewrite cả file); đẩy watermark; chạy `llm-wiki reindex` (tăng dần).
10. **Báo cáo**: concept nào được gộp, bản nào deprecate, citation trước/sau, phần nào cần human duyệt.

## Không làm

- Không co / mất citation. Không xoá nội dung của người. Không nâng `verified` thay người.
- Không xoá file concept — chỉ deprecate + con trỏ.
- Không gộp vượt quá `cap` một lần: nhiều topic → chạy từng topic, mỗi topic một lần reindex + báo cáo riêng.
