---
name: wiki-project-plan
description: Plan mode workflow cho task lớn trong project codebase. Research wiki → identify gaps → propose plan → cite wiki sources. Project-wiki skill. Dùng khi user bảo "plan cái này", "refactor X", hoặc bất kỳ task multi-file.
---

# Wiki Project — Plan

Companion của `wiki-project-research`. Skill này operationalize quy trình plan mode cho project-wiki context.

## Workflow

1. **Enter plan mode** (Shift+Tab trong Claude Code / OpenCode).
2. **Research via `wiki-project-research`** skill — thu thập context từ wiki.
3. **Identify gaps** — wiki thiếu gì, cần đọc code trực tiếp chỗ nào.
4. **Spawn explore agents** (parallel) để fill gaps — mỗi agent đi 1 hướng.
5. **Synthesize plan** tại `~/.commandcode/plans/<descriptive>.md`.
6. **Cite wiki pages** trong plan: dùng pattern `[[wiki/<domain>/...]]`.
7. **Exit plan mode** — user review + approve.
8. **Post-implement**: update wiki với new pattern / file / gotcha.

## Plan format

Plan nên có cấu trúc:

- **Goal** — 1 câu tóm tắt task.
- **Wiki context** — list các page đã research: `[[wiki/architecture/...]]`, `[[wiki/conventions/...]]`. Đây là reference cho mọi claim trong plan.
- **Gaps** — wiki thiếu gì, cần verify bằng code/grep.
- **Approach** — outline từng bước implement. Mỗi bước cite wiki path nếu dùng convention từ wiki.
- **Verification** — phải reference wiki path: "verify bằng `wiki_search('auth flow')`" hoặc "grep X theo convention tại `[[wiki/conventions/...]]`".
- **Wiki update** — list page cần update sau khi implement (new pattern, new gotcha).

## Nguyên tắc

- **Cite ngay từ đầu**: mỗi claim quan trọng → cite wiki page hoặc URL.
- **Nếu wiki thiếu** → flag trong plan, đề xuất ingest sau (qua `wiki_submit`).
- **Verification phải reproducible** — dùng MCP tool hoặc shell command, không vague "test thử".
- **Out of scope explicit** — list gì KHÔNG làm, tránh scope creep.

## Plan mode integration

- Trong plan mode, KHÔNG được sửa code/file. Chỉ research + write plan.
- Cite wiki = `[[wiki/<domain>/kind/slug]]` (full path, không dùng markdown link bọc wikilink).
- Nếu cần verify bằng shell: dùng command trong plan, không exec.

## An toàn

- **Contradiction giữa plan và wiki** → ưu tiên wiki (đã có provenance). Flag conflict cho human.
- **Multi-domain refactor** → cần wiki context từ N domain, research đủ rồi mới plan.
- **Breaking change** → explicit "Breaking:" section trong plan, không giấu trong prose.
