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
   - Hybrid: `wiki_search(query, top_k)` (BM25 FTS5 + vector fastembed). Mỗi result có `domain` + `kind` — dùng để filter/hiển thị theo domain.
   - Semantic chunk: `semantic_search(query, top_k)` (rag/.rag_index).
   - Hoặc đọc `wiki/index.md` rồi drill vào domain index (`wiki/<domain>/index.md`).
   - Filter theo domain: `wiki_list(domain="expo-ecosystem")` hoặc `wiki_list(kind="concept")`.
2. Đọc page liên quan (`wiki_read`) để lấy chi tiết + provenance.
3. Tổng hợp câu trả lời, **cite** nguồn: `[[wiki/<domain>/source/...]]` hoặc `raw/...`.
4. Nếu câu hỏi cần synthesis mới (so sánh, connection): **file ngược thành page mới** trong domain phù hợp (`wiki/<domain>/concept/...`) + index tiếp → wiki compounding.

## MCP tools (đọc / tìm kiếm wiki)
- `wiki_search` · `semantic_search` · `wiki_read` · `wiki_list(domain, kind)`.
- `wiki_list` trả mỗi entry có `path, title, domain, kind`. Domain là top-level folder.

## Nạp context (AI khác)
AI khác không query ở đây — chúng dùng `wiki_submit` (với `domain` optional) để đẩy context vào `raw/inbox/`, maintainer ingest sau.

## An toàn
- Contradiction giữa pages → báo human, không tự quyết hay ghi edge.
- Không bịa claim không có trong wiki/raw.
- Cross-domain synthesis: nếu page synthesis trải nhiều domain, đặt vào domain nào user đang quan tâm nhất (hoặc tạo domain mới nếu chủ đề chưa có).
