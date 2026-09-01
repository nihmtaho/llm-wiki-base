---
name: ingest
description: >
  Đưa nguồn mới vào bundle, tích hợp thành concept theo SCHEMA.md (OKF v0.2), rồi reindex tăng dần ngay.
  Kích hoạt khi có file mới trong raw/, hoặc khi người dùng nói "ingest", "thu nạp nguồn này".
---

# Skill: ingest

Mục tiêu: biến nguồn thô thành/ cập nhật concept, giữ provenance, không phá nội dung người, và giữ chỉ mục search đồng bộ ngay.

## Điều kiện trước
- Đọc `SCHEMA.md` + `wiki.config.toml` (profile, quy ước field, `[retrieval]`).
- Nguồn nằm trong `raw/` (bất biến). Không sửa file trong `raw/`.

## Quy trình
1. **Đọc trọn nguồn.** Tóm tắt 3–5 takeaway, bàn với người trước khi ghi (mặc định ingest từng nguồn một).
2. **Plan concept đích.** Với mỗi target: tra `registry.yml` — đã `planned`/`active` → **update**, không create. Nếu create → RESERVE placeholder `status: planned` trước khi sinh (claim ID bằng ghi có điều kiện, reasoning ngoài lock).
3. **Phân loại (codebase).** Intent → `requirements/`; observation từ code → `modules/`. Không rõ intent → open question vào `alerts/`, KHÔNG bịa.
4. **Ghi concept theo SCHEMA §5:** frontmatter (`type`, `title`, `sources[]` trỏ `raw/…`, `generated`, `status: draft`, `tags`, `x_owner`); **để trống `verified`** (chờ người). Body: TL;DR + cấu trúc + footnote `sources[].id` kèm trích verbatim. Link concept↔concept bằng wikilink theo Concept ID; URL dùng markdown link.
5. **Tôn trọng pins** (`pins.yml`): pin `active` phải giữ. Nguồn mới mâu thuẫn pin → KHÔNG ghi đè; đẩy vào `alerts/`.
6. **Cập nhật catalog:** thêm mục `index.md`; placeholder registry `planned → active`; append `log.md` (`## [<ISO8601>] ingest | <title>`).
7. **Reindex ngay (mới):** cập nhật `.wiki-index/` **tăng dần** cho đúng các concept vừa tạo/sửa (theo content-hash, không rebuild toàn bộ), theo `[retrieval.index]`. Nếu `rebuild="on-ingest"` → chạy tự động; nếu `vector=true` → embed các chunk mới; nếu thiếu embed_model → chỉ cập nhật BM25/structural và báo "vector skipped".
8. **Báo cáo:** concept đã tạo/sửa, đã reindex những gì, và phần cần người duyệt (`verified`).

## Không làm
- Không tái sinh concept từ concept (chỉ raw → concept). Không xóa nội dung người. Không set `verified` thay người.
- Không commit `.wiki-index/`.
