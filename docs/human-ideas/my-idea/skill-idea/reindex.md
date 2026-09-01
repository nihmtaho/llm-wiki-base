---
name: reindex
description: >
  Dựng/làm mới chỉ mục search derived (.wiki-index/) từ markdown: BM25 + (tùy chọn) vector + semantic chunks.
  Tăng dần theo content-hash; có full rebuild và dry-run. KHÔNG commit. Kích hoạt định kỳ, sau ingest, hoặc khi lint báo lệch.
---

# Skill: reindex

Mục tiêu: giữ `.wiki-index/` đồng bộ với markdown. Markdown là nguồn sự thật; chỉ mục là derived, vứt đi rebuild được.

## Điều kiện trước
- Đọc `[retrieval]` và `[retrieval.index]` trong `wiki.config.toml`.
- `.wiki-index/` PHẢI gitignored. Không bao giờ commit.

## Chế độ
- `reindex`          — tăng dần (mặc định): chỉ xử lý concept đổi/mới/xóa.
- `reindex --full`   — rebuild toàn bộ từ đầu (khi đổi `chunk_tokens`/`embed_model`, hoặc index hỏng).
- `reindex --check`  — dry-run: báo lệch giữa markdown và index, KHÔNG ghi.

## Quy trình (tăng dần)
1. **Liệt kê concept:** mọi `.md` không phải `index.md`/`log.md`. Tính **content-hash** mỗi concept.
2. **So với hash đã lưu** trong `.wiki-index/`:
   - mới / đổi → re-chunk + reindex.
   - xóa → gỡ chunk của concept đó khỏi BM25 + vector.
   - không đổi → bỏ qua (đây là chỗ tăng dần tiết kiệm).
3. **Semantic chunking:** cắt body theo ranh giới section (~`chunk_tokens`), giữ heading làm ngữ cảnh. **Loại:** footnote/bằng chứng verbatim, frontmatter thô, `raw/**`, và `[private] dirs` (index nhưng không commit — vẫn nằm trong `.wiki-index/` local).
4. **BM25:** cập nhật bảng full-text cho chunk đổi (luôn chạy, không cần model).
5. **Vector (chỉ khi `vector=true` và `embed_model` có):** embed chunk mới/đổi; xóa vector của chunk gỡ. Thiếu `embed_model` → bỏ qua vector, báo `vector skipped`, BM25/structural vẫn đủ.
6. **Structural:** làm mới đồ thị wikilink + đối chiếu `index.md` với file thực (báo nếu lệch — sửa index.md là việc của `lint`, không phải ở đây).
7. **Ghi metadata index:** hash mới, số chunk, thời điểm, cấu hình đã dùng (để `--check` và `lint` phát hiện lệch cấu hình).
8. **Báo cáo:** N concept indexed, chunk +/−, vector on/off, drift đã xử lý.

## Quan hệ với skill khác
- `ingest`/`consolidate` gọi reindex **tăng dần** cho phần vừa đổi.
- `lint` chỉ *phát hiện* `.wiki-index/` lệch; `reindex` *sửa*.
- Đổi `chunk_tokens`/`embed_model`/bật-tắt vector → phải `reindex --full`.

## Không làm
- Không commit `.wiki-index/`. Không sửa markdown. Không coi index là nguồn sự thật.
