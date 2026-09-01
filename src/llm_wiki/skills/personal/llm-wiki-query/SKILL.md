---
name: llm-wiki-query
description: Query LLM wiki — search (hybrid BM25+vector hoặc semantic chunk), filter theo domain/kind, tổng hợp trả lời có cite. Dùng khi human hỏi về kiến thức đã ingest.
---

# LLM Wiki — Query

Schema: `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào
Human đặt câu hỏi về nội dung đã có trong wiki.

## Quy trình
1. Tìm relevant pages:
   - Hybrid: `wiki_search(query, top_k, wiki="")` (BM25 FTS5 + vector fastembed). Mỗi result có `domain` + `kind` + `wiki` — dùng để filter/hiển thị. Để `wiki=""` để search all wikis (cross-scope), hoặc `wiki="<name>"` để target cụ thể.
   - Semantic chunk: `semantic_search(query, top_k, wiki="")` (rag/.rag_index).
   - Hoặc đọc `wiki/index.md` rồi drill vào domain index (`wiki/<domain>/index.md`).
   - Filter theo domain: `wiki_list(domain="expo-ecosystem", wiki="")` hoặc `wiki_list(kind="concept", wiki="")`.
2. Đọc page liên quan (`wiki_read`) để lấy chi tiết + provenance.
3. Tổng hợp câu trả lời, **cite** nguồn: `[[wiki/<domain>/source/...]]` hoặc `raw/...`.
4. Nếu câu hỏi cần synthesis mới (so sánh, connection): **file ngược thành page mới** trong domain phù hợp (`wiki/<domain>/concept/...`) + index tiếp → wiki compounding.

## MCP tools (đọc / tìm kiếm wiki)

Centralized MCP server (`llm-wiki-base-mcp`) — mỗi tool có param `wiki=`:
- `wiki=""` → cross-wiki (all wikis). `wiki="<name>"` → target cụ thể.
- `wiki_search(query, top_k, wiki="")` · `semantic_search(query, top_k, wiki="")`
- `wiki_read(path, wiki="")` · `wiki_list(domain, kind, wiki="")`.
- Kết quả search/read luôn gán `wiki` field để biết nguồn gốc.

## Nạp context (AI khác)
AI khác không query ở đây — chúng dùng `wiki_submit` (với `domain` optional) để đẩy context vào `raw/inbox/`, maintainer ingest sau.

## An toàn
- Contradiction giữa pages → báo human, không tự quyết hay ghi edge.
- Không bịa claim không có trong wiki/raw.
- Cross-domain synthesis: nếu page synthesis trải nhiều domain, đặt vào domain nào user đang quan tâm nhất (hoặc tạo domain mới nếu chủ đề chưa có).
