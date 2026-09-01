---
name: lint
description: >
  Kiểm tra sức khỏe cấu trúc bundle (tất định) và sửa an toàn; các vấn đề ngữ nghĩa để cho review.
  Kích hoạt định kỳ hoặc khi người dùng nói "lint", "kiểm tra wiki".
---

# Skill: lint

Nguyên tắc: **tất định trước, sinh sinh sau.** Skill này chỉ lo phần tất định (cấu trúc); mâu thuẫn/claim cũ/khái niệm thiếu là việc của `review`.

## Kiểm tra (deterministic) — chạy tất cả, gom kết quả
### Conformance OKF
- Mọi `.md` không phải `index.md`/`log.md` PHẢI có frontmatter YAML hợp lệ + `type` không rỗng.
- `index.md`/`log.md` viết thường; chỉ `index.md` gốc được khai `okf_version`.
- Timestamp là ISO-8601 có offset UTC.
- Concept ID (path bỏ `.md`) là duy nhất — không trùng.

### Link
- Wikilink trỏ tới Concept ID **tồn tại**; báo wikilink gãy.
- Concept↔concept dùng markdown link thay wikilink → cảnh báo (đề xuất convert).
- URL dùng wikilink → cảnh báo.

### Provenance & catalog
- Mọi footnote `[^id]` khớp một `sources[].id`; và ngược lại `sources` có `id` thì nên được cite.
- `index.md` đồng bộ với file thực (thiếu mục / mục thừa / mô tả cũ).
- `registry.yml`: placeholder `planned` quá hạn mà chưa thành `active` (reservation cũ).
- `pins.yml`: pin có `anchor` trỏ section không còn tồn tại → orphan.

### Layout (g3doc)
- Concept thiếu `x_owner`.
- Dấu hiệu trộn nhiều `type`/mục đích trong một file.
- Dense bullet (>3 mục dồn một dòng), thụt lề quá 3 cấp.

## Sửa an toàn (auto-fix)
- Rebuild danh sách trong `index.md` theo file thực.
- Chuẩn hoá timestamp về ISO-8601 offset.
- Convert link sai dạng: concept↔concept → wikilink theo Concept ID; (tùy chọn export) wikilink → markdown link.
- Đánh dấu orphan pin / stale reservation (không tự xóa).

## Báo cáo
- In hai nhóm: **đã sửa** và **cần người xử lý** (mâu thuẫn, thiếu owner, section mất, mâu thuẫn pin). Chuyển nhóm ngữ nghĩa sang `review`.

## Không làm
- Không sửa nội dung mang nghĩa (đó là `review`).
- Không xóa concept, pin, hay reservation của người khác.
