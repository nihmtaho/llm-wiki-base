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
2. **`wiki_search`** (MCP) — union retrieval: BM25 page ∪ BM25 chunk ∪ vector chunk, gộp bằng **RRF trên hạng**. Xin pool **rộng hơn** số cần đọc: `top_k = 2 × [retrieval].top_n_final` (config ở `.llm-wiki.toml`). `vector = false` → tự degrade sang 2 kênh text, vẫn chạy. Query không match AND → tool tự nới (AND sanitize → OR) khi `relax_recall = true`.
3. **Rerank (skill làm)** — khi `[retrieval].rerank = "llm"`: chấm ứng viên chỉ bằng `title` + `snippet` + `matched_by` (KHÔNG mở file), rồi chọn đúng `top_n_final` page để đọc. Tiêu chí: (a) đúng chủ đề chứ không chỉ trùng từ; (b) `matched_by` nhiều kênh = đáng tin hơn; (c) trust tier — ưu tiên `verified.by: human:*`; (d) trùng chủ đề → giữ page canonical (`concept`, không phải `source`/`index`). `rerank = "off"` → giữ nguyên thứ tự RRF.
4. **Đọc relevant pages** (`wiki_read`) — note paths, conventions, gotchas. **Trust tier check** (cả personal + project): page `status: draft`/không `verified` → coi như unverified, cross-check với code trước khi tin; `stale_after` quá hạn → coi là stale.
5. **Cross-check với code** qua `codegraph` (nếu có) — verify wiki vẫn còn đúng (không stale).
6. **Update wiki** nếu phát hiện thiếu hoặc sai (qua `wiki_propose_edit`).

## Đo chất lượng retrieval

`llm-wiki eval --compare` (chạy từ project-wiki dir) in P@k / R@k / MRR cho 3 profile
`tier1-weighted` / `rrf-text` / `rrf+vector` — đó là **bằng chứng** để bật
`[retrieval].vector`, không phải cảm giác. Query vàng ở `eval/golden.toml` (commit);
kết quả đo ở `eval/results.json` (gitignored). Thêm query vàng từ các câu hỏi thật
của dev trong phiên + `wiki/log.md`. `zero_recall_queries` = wiki thiếu tài liệu →
việc của `wiki-project-ingest`, không phải của retriever.

## MCP tools (centralized — dùng `wiki` param để target project wiki)

Centralized MCP server (`llm-wiki-base-mcp`) phục vụ toàn bộ wikis trên máy.
Để target project wiki cụ thể, dùng param `wiki=<project-wiki-name>`:

- `wiki_search(query, top_k=16, wiki="project-wiki")` — union retrieval + RRF trong project wiki; `top_k` là số ứng viên (rerank ở bước 3 mới cắt xuống `top_n_final`). Để `wiki=""` để search all wikis (cross-scope).
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
