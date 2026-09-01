---
title: Wiki Log
domain: wiki
kind: log
updated: 2026-08-30
status: active
---

# Wiki Log

Append-only, reverse-chronological (mới nhất trên cùng). Mỗi entry format:

```
## [YYYY-MM-DD HH:MM:SS] <op> | <title>

- source: <raw source path hoặc URL>
- sources: <wiki pages dùng làm reference>
- tạo: <files mới>
- update: <files sửa>
- skipped: <actions đã cân nhắc nhưng không thực hiện>
```

`<op>` ∈ `ingest` | `wiki_lint` | `migrate` | `fix`. Chỉ viết action thực sự có — bỏ bullet nếu không có.

---

<!-- entries go above this line -->
