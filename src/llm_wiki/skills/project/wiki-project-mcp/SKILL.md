---
name: wiki-project-mcp
description: Centralized MCP (llm-wiki-base-mcp) bridge cho project wiki scope. Target wiki cụ thể qua param `wiki=<name>`, hoặc search cross-wiki (bao gồm cả personal wiki). MCP chỉ được phép research + contribute — KHÔNG ingest.
---

# Wiki Project — Centralized MCP

## Centralized MCP là gì

Thay vì cài 1 MCP server mỗi wiki, toàn bộ wikis trên máy chạy qua **một** MCP server duy nhất:
`llm-wiki-base-mcp` (config 1 entry trong Claude Code / OpenCode / Zed).

Server đọc `~/.llm-wiki-base/registry.toml` để biết danh sách wikis. Mỗi wiki là 1 entry:
```toml
[[wikis]]
name = "my-project"
path = "/Users/me/projects/my-app/project-wiki"
type = "project"
added = "2026-09-01T10:00:00"
```

## Khi nào dùng

- Research kiến thức từ **bất kỳ wiki nào** trên máy (project wiki, personal wiki, wiki khác).
- Cross-check thông tin giữa các wiki.
- Nạp nguồn mới vào inbox của **một wiki cụ thể** do human chỉ định.
- Đề xuất sửa wiki (staging, chờ human sign-off).

## Targeting wiki

Mọi MCP tool đều có param `wiki=` (tên wiki trong registry):

| Pattern | Hành động |
|---|---|
| `wiki_search(query, wiki="my-project")` | Search trong 1 wiki duy nhất. |
| `wiki_search(query)` | **Cross-wiki search** — search ALL wikis, kết quả gán `wiki` field để phân biệt. |
| `wiki_read(path, wiki="my-project")` | Đọc file từ 1 wiki cụ thể. |
| `wiki_read(path)` | Tìm path trong ALL wikis (lỗi nếu trùng ở nhiều wiki). |

**Quy tắc:** để `wiki` rỗng → cross-wiki (ưu tiên cho research). Điền `wiki` → target cụ thể (bắt buộc cho write tools).

## Cross-scope search (từ project wiki sang personal wiki)

Từ project codebase, AI có thể tìm kiếm cả personal wiki (knowledge cá nhân) mà không cần chuyển context:

```
# Search trong project wiki + personal wiki + tất cả wikis khác
wiki_search("design pattern authentication")

# Search chỉ trong project wiki
wiki_search("architecture decision record", wiki="my-project")

# Đọc một page từ personal wiki khi đang ở project context
wiki_read("wiki/tech/concept/auth-patterns.md", wiki="my-knowledge")
```

Kết quả luôn được gán `wiki` field để AI biết nguồn gốc.

## MCP tools (centralized)

- `wiki_search(query, top_k, wiki="")` — union retrieval (BM25 page ∪ BM25 chunk ∪ vector chunk) + **RRF fusion**; mỗi kết quả có `matched_by` (kênh nào tìm ra) + `rank`. `top_k` = số kết quả CUỐI, `0` = theo `[retrieval].top_n_final`. `wiki=""` → all wikis (gộp cross-wiki cũng bằng RRF trên hạng-per-wiki).
- `semantic_search(query, top_k, wiki="")` — chunk-level vector thô (cần `vector = true` + reindex). `wiki=""` → all wikis. **Chỉ để tìm concept**, đừng trích chunk làm câu trả lời.
- `wiki_read(path, wiki="")` — đọc file. `wiki=""` → tìm trong all wikis.
- `wiki_list(domain, kind, category, wiki="")` — list pages. `wiki=""` → all wikis.
- `list_raw_source(subdir, wiki="")` — list raw sources.
- `read_raw_source(name, subdir, wiki="")` — đọc raw source để cite.
- `wiki_submit(title, content, wiki, domain, source, category)` — **bắt buộc `wiki`**. Ghi vào `raw/inbox/` của wiki đó.
- `wiki_propose_edit(path, content, wiki)` — **bắt buộc `wiki`**. Staging vào `.proposals/`.
- `wiki_lint(wiki="")` — health check. `wiki=""` → lint all wikis.

## Registry management

```bash
llm-wiki wiki list           # list all registered wikis
llm-wiki wiki add <name> <path> --type project   # register wiki đã có sẵn
llm-wiki wiki remove <name>  # xóa khỏi registry (không xóa files)
```

Wiki được tự động đăng ký khi chạy `llm-wiki init` (personal hoặc project). Dùng `wiki add` để đăng ký wiki đã tồn tại.

## Safety: MCP KHÔNG ingest

**Nguyên tắc bắt buộc:** MCP chỉ được phép:
1. **Research** — search + read (wiki_search, wiki_read, wiki_list, semantic_search, wiki_lint).
2. **Contribute** — nạp ngữ cảnh vào wiki do **human chỉ định** (wiki_submit → raw/inbox/, wiki_propose_edit → .proposals/).

**MCP KHÔNG được:**
- Ingest (chạy pipeline tạo/update wiki pages trong `wiki/`).
- Ghi thẳng vào `wiki/` — chỉ staging qua inbox hoặc proposals.
- Tự chọn wiki để write — luôn cần `wiki=` param (human phải chỉ định).

Ingest là maintainer-only: `llm-wiki ingest` (CLI) hoặc `llm-wiki-ingest` skill.

## Resources

Centralized MCP server cung cấp resources để đọc nhanh:

- `registry://wikis` — list tất cả wikis trong registry.
- `wiki://<name>/index` — top-level index của 1 wiki.
- `wiki://<name>/log` — append-only log của 1 wiki.

Dùng khi client hỗ trợ resource attachment (Claude Code tự động fetch khi context cần).

## An toàn

- **AI proposes, human decides.** Wiki submit → inbox, propose edit → proposals, chờ human duyệt. MCP không tự động ingest.
- **Cross-wiki search không bị nhầm lẫn** — mỗi kết quả đều gắn `wiki` field. Đọc page cụ thể luôn chỉ định `wiki=` để tránh ambiguity.
- **Contradiction giữa wikis** → báo human, không auto-resolve.
- **Path traversal chặn** — MCP server reject mọi path ngoài wiki root (`_resolve_in_wiki`).
```
