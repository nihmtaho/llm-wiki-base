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
2. **`wiki_search`** (MCP) với query liên quan — hybrid BM25 + vector (nếu `[retrieval].vector = false` trong `.llm-wiki.toml` → tự degrade BM25-only, vẫn chạy). AND-match 0 kết quả → tool tự retry OR (relax_recall).
3. **Đọc relevant pages** (`wiki_read`) — note paths, conventions, gotchas. Đọc tối đa `[retrieval].top_n_final` concept (default 8). **Trust tier check** (cả personal + project): page `status: draft`/không `verified` → coi như unverified, cross-check với code trước khi tin; `stale_after` quá hạn → coi là stale; ưu tiên human-reviewed (`verified.by: human:*`).
4. **Cross-check với code** qua `codegraph` (nếu có) — verify wiki vẫn còn đúng (không stale).
5. **Update wiki** nếu phát hiện thiếu hoặc sai (qua `wiki_propose_edit`).

## MCP tools (centralized — dùng `wiki` param để target project wiki)

Centralized MCP server (`llm-wiki-base-mcp`) phục vụ toàn bộ wikis trên máy.
Để target project wiki cụ thể, dùng param `wiki=<project-wiki-name>`:

- `wiki_search(query, top_k=8, wiki="project-wiki")` — hybrid search trong project wiki. Để `wiki=""` để search all wikis (cross-scope).
- `wiki_read(path, wiki="project-wiki")` — đọc page (path relative to wiki root, vd `wiki/architecture/auth-flow.md`).
- `wiki_list(domain, kind, wiki="project-wiki")` — list pages, filter theo domain/kind.
- `semantic_search(query, wiki="project-wiki")` — chunk-level vector search (cần `rag/index.py` build).
- `wiki_submit(title, content, wiki="project-wiki", domain, source)` — nạp raw source mới vào `raw/inbox/`. **Bắt buộc chỉ định `wiki`**.
- `wiki_propose_edit(path, content, wiki="project-wiki")` — đề xuất sửa wiki page (staging). **Bắt buộc chỉ định `wiki`**.

> Tên project wiki = tên subfolder (mặc định `project-wiki`). Chạy `llm-wiki wiki list` để xem tên.
> Để `wiki=""` để **cross-wiki search** (bao gồm cả personal wiki) — hữ useful khi cần kiến thức cá nhân.

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
- `wiki_submit(title, content, wiki="project-wiki", domain, source)` — nạp raw source vào `raw/inbox/`. **Bắt buộc chỉ định `wiki`**. Maintainer (LLM agent khác hoặc user) sẽ ingest sau.
- `wiki_propose_edit(path, content, wiki="project-wiki")` — đề xuất sửa, staging vào `wiki/.proposals/`, chờ human sign-off. **Bắt buộc chỉ định `wiki`**.

## An toàn

- **Centralized MCP, shared server.** Server `llm-wiki-base-mcp` phục vụ toàn bộ wikis trên máy.
  Luôn dùng param `wiki=<name>` để target project wiki — đừng để `wiki=""` khi mục đích
  chỉ ở project wiki (cross-wiki search trả kết quả từ nhiều wiki, cần phân biệt).
  Dùng `llm-wiki wiki list` để kiểm tra tên wiki đã đăng ký.
- **Project wiki ≠ personal wiki.** Nhưng với centralized MCP, AI có thể cross-wiki search
  (personal wiki bao gồm) khi để `wiki=""` — hữ useful, nhưng phải biết phân biệt nguồn.
- **Wiki có thể stale.** Luôn cross-check critical claim với code qua `codegraph` hoặc grep.
- **Contradiction giữa wiki pages → báo human**, không tự resolve.
- **MCP không ingest.** Chỉ search/read/propose. Ingest là maintainer-only.
