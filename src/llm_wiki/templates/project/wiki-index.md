---
title: Wiki Index
domain: wiki
kind: index
updated: 2026-08-30
status: active
---

# Wiki Index

Artifact tích luỹ do LLM maintain. **Domain = top-level folder** dưới `wiki/`, auto-detect từ nội dung raw. Số lượng domain không cố định. Khi ingest gặp chủ đề mới, agent tạo folder mới theo naming rule (kebab-case) rồi thêm row vào bảng dưới.

| Domain | Mô tả | Pages | Index |
|---|---|---|---|
| (chưa có) | | 0 | — |

## Naming rule cho domain mới

- 1 framework/library rõ ràng → kebab-case tên (`expo-ecosystem`, `react-navigation`, `claude-code`).
- 1 giáo trình / series → kebab-case tên series (`minna-no-nihongo`).
- 1 dự án nội bộ → kebab-case tên project (`my-project`).
- Lĩnh vực rộng chưa rõ project → tạo mới với tên mô tả (vd: `distributed-systems`).

Mỗi domain có cấu trúc: `index.md` + `entity/` + `concept/` + `source/` (+ `task/` nếu cần task tracking, + sub-folder tuỳ ngữ cảnh như `vocab/` cho language domain).

**Khi thêm domain mới:** tạo `wiki/<domain>/` + `index.md`, rồi thêm 1 row vào bảng trên. Count pages = `find wiki/<domain> -name "*.md" | wc -l`.

---

Log: [log.md](log.md) · Schema: [AGENTS.md](../AGENTS.md) · Runbook: [CLAUDE.md](../.claude/CLAUDE.md)
