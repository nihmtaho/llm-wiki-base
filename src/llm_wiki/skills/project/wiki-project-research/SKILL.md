---
name: wiki-project-research
description: Research codebase bằng project wiki (ưu tiên) + codegraph (fallback). Dùng khi cần tìm hiểu tech stack, architecture, hoặc trước khi bắt đầu task lớn. Project-wiki skill — KHÔNG dùng cho personal wiki.
---

# Wiki Project — Research

Mọi project codebase có 1 project wiki song song tại `<project>/project-wiki/`. Khi cần research tech stack / architecture / convention của project, **luôn ưu tiên wiki trước khi đọc code thô**.

## Khi nào dùng

- Bắt đầu task mới: hiểu project structure, patterns, dependencies.
- User hỏi "project này dùng stack gì", "auth flow hoạt động ra sao", "convention test thế nào".
- Cần tìm 1 file/function: thử wiki trước (có thể đã có summary + path), rồi mới grep.
- Trước khi viết code mới: check xem wiki có hướng dẫn / pattern chưa.

## Workflow

1. **Đọc `<project>/project-wiki/wiki/index.md`** để biết có những domain nào (tech-stack, architecture, conventions, ...).
2. **`wiki_search`** (MCP) với query liên quan — hybrid BM25 + vector.
3. **Đọc relevant pages** (`wiki_read`) — note paths, conventions, gotchas.
4. **Cross-check với code** qua `codegraph` (nếu có) — verify wiki vẫn còn đúng (không stale).
5. **Update wiki** nếu phát hiện thiếu hoặc sai (qua `wiki_propose_edit`).

## MCP tools (project-wiki only)

- `wiki_search(query, top_k=8)` — hybrid search trong `<project>/project-wiki/wiki/`.
- `wiki_read(path)` — đọc page (path relative to project-wiki root, vd `wiki/architecture/auth-flow.md`).
- `wiki_list(domain, kind)` — list pages, filter theo domain hoặc kind.
- `semantic_search(query)` — chunk-level vector search (cần `rag/index.py` đã build).
- `wiki_submit(title, content, domain, source)` — nạp raw source mới vào `raw/inbox/`.
- `wiki_propose_edit(path, content)` — đề xuất sửa wiki page (staging, chờ human sign-off).

## Plan mode

**Với task lớn / phức tạp (refactor, new feature, multi-file change):**
1. Research wiki trước → thu thập context.
2. Switch sang **plan mode** (Shift+Tab) trước khi code.
3. Trong plan: cite wiki pages làm reference, identify gaps, propose approach.
4. Sau khi implement → update wiki (the new pattern / file / gotcha).

**Với task nhỏ (typo, single-line fix):** skip plan mode, dùng wiki làm context.

**Companion skill:** `wiki-project-plan` operationalize plan mode cho project-wiki context.

## Ưu tiên research

1. **Wiki (`wiki_search` / `wiki_read`)** — đã được curated, có provenance, nhanh.
2. **`codegraph`** (nếu cài) — graph call/import, cho navigation tốt hơn grep.
3. **`grep` / `find`** — fallback cuối cùng.

KHÔNG nhảy thẳng vào `grep` khi wiki chưa được check. Wiki mất công maintain, dùng nó.

## Nạp context mới

Nếu wiki thiếu thông tin, KHÔNG tự ý ghi trực tiếp. Dùng:
- `wiki_submit(title, content, domain, source)` — nạp raw source vào `raw/inbox/`. Maintainer (LLM agent khác hoặc user) sẽ ingest sau.
- `wiki_propose_edit(path, content)` — đề xuất sửa, staging vào `wiki/.proposals/`, chờ human sign-off.

## An toàn

- **Project wiki ≠ personal wiki.** Skill này chỉ hoạt động khi MCP server trỏ tới `<project>/project-wiki/`. Đừng nhầm với personal wiki (skill `llm-wiki-{ingest,query,lint}`).
- **Wiki có thể stale.** Luôn cross-check critical claim với code qua `codegraph` hoặc grep trước khi hành động.
- **Contradiction giữa wiki pages → báo human**, không tự resolve.
- **Multi-project trên cùng máy**: nếu có nhiều project-wiki, check `WIKI_ROOT` env của MCP server session hiện tại trước khi `wiki_read` (path khác nhau).
