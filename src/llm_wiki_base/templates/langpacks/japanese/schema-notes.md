# Japanese pack — bổ sung cho `_schema.md`

> Tài liệu tham khảo cho người giữ wiki — KHÔNG được tự động append vào
> `_schema.md` (kể cả khi `[langpack]` bật: `enabled = true`,
> `pack = "japanese"`). Agent học required fields qua lint
> `langpack-field-missing`.

## Kinds (japanese)

### `grammar-point/` — trang điểm ngữ pháp

| field | required | enum / format | ghi chú |
|---|---|---|---|
| `pattern` | **yes** | chuỗi | pattern thật: `〜てから`, `〜たら` |
| `meaning` | **yes** | chuỗi | nghĩa tiếng Việt |
| `reading` | no | kana | |
| `register` | no | `casual` \| `polite` \| `formal` \| `written` | |
| `jlpt` | no | `N5` \| `N4` \| `N3` \| `N2` \| `N1` | |
| `tags` | no | list | |

### `vocab/` — trang từ vựng

| field | required | enum / format | ghi chú |
|---|---|---|---|
| `word` | **yes** | chuỗi | từ tiếng Nhật |
| `reading` | **yes** | kana | |
| `meaning` | **yes** | chuỗi | nghĩa tiếng Việt |
| `jlpt` | no | chuỗi | |
| `register` | no | chuỗi | |

Field thiếu → lint `langpack-field-missing` (CRITICAL, không auto-fix).

## Slug rule (japanese)

- Slug của `grammar-point` derive từ pattern đã chuẩn hóa (`ba-tara.md`,
  `te-kara.md`) — **KHÔNG BAO GIỜ** từ tên sách + bài.
- Tên sách + bài chỉ sống trong **source page** và relation `covered-in`
  (`covered-in: {targets: [source]}` — dst phải trỏ vào `.../source/...`).
- Slug chứa tên giáo trình (Shinkanzen, Minna, …) → lint style advisory.

## Relations (vocabulary của pack)

| rel | ràng buộc |
|---|---|
| `contrast-with` | — |
| `example-of` | — |
| `synonym-of` | — |
| `derived-from` | — |
| `covered-in` | `targets: [source]` — dst phải là `source/` path |
| `related` | default cho plain wikilink `[[path]]` |

Rel không có trong bảng trên → lint `unknown-rel-type` (CRITICAL).
Wiki không bật pack → không ràng buộc nào áp dụng.

## `## Claims` (atomic facts)

Mỗi bullet = một claim atom = đúng một câu, ≥1 footnote `[^id]` → `sources:`.
Footnote giữ nguyên ngữ nghĩa trích dẫn nguyên văn (lint
`footnote-sources-match` không đổi).

Ví dụ (grammar-point `〜たら`):

```markdown
## Claims

- 〜たら dùng để chỉ việc "sau khi X xảy thì Y" với sắc thái tình cờ, không chủ đích.[^s1]
- 〜たら có thể dùng cho điều kiện tương lai "nếu X thì Y", thay thế 〜ば trong nói.[^s1]
- Shinkanzen N3 bài 6 xếp 〜たら vào nhóm điều kiện, không nhóm "sau khi".[^s2]
```

- Claim-vs-claim dùng inline anchor:
  `- 〜ば nhấn điều kiện logic.[^s2] [[wiki/languages/grammar-point/ba.md#claims|rel:contradicts]]`
- Nguồn mới **đồng ý** claim cũ → thêm footnote mới vào claim đó (tăng provenance).
- Nguồn mới **mâu thuẫn** → KHÔNG sửa claim cũ; thêm `rel: contradicts` trỏ
  claim mới + mở `wiki/alerts/` (mâu thuẫn để human resolve).
