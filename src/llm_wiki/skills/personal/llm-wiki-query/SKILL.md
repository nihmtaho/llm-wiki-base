---
name: llm-wiki-query
description: Query LLM wiki — union retrieval (BM25 page + BM25 chunk + vector chunk, RRF) rồi rerank bằng LLM, filter theo domain/kind, tổng hợp trả lời có cite. Dùng khi human hỏi về kiến thức đã ingest.
---

# LLM Wiki — Query

Schema: `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào
Human đặt câu hỏi về nội dung đã có trong wiki.

## Quy trình
1. **Định tuyến structural**: đọc `wiki/index.md` → domain index (`wiki/<domain>/index.md`). Route tốt nhất khi đã biết domain; bỏ qua nếu không rõ.
2. **Lấy pool ứng viên RỘNG hơn số cần đọc**:
   - `wiki_search(query, top_k=2 × top_n_final, wiki="")` — union retrieval: BM25 page ∪ BM25 chunk ∪ vector chunk, gộp bằng **RRF trên hạng**. Đọc `[retrieval]` trong `.llm-wiki.toml`.
   - Query tiếng Việt/hỗn hợp ký tự đặc biệt: tool tự nới (giữ nguyên → AND sanitize → OR) khi `relax_recall = true`.
   - `semantic_search(query, top_k, wiki="")` khi cần xem riêng chunk-level vector (chỉ có khi `vector = true`).
   - Filter: `wiki_list(domain="...", kind="concept", wiki="")`.
3. **RERANK ở bước này (skill làm, không phải tool)** — khi `[retrieval].rerank = "llm"`:
   - Chỉ dùng `title` + `snippet` + `matched_by` của mỗi ứng viên; **KHÔNG mở file** lúc chấm.
   - Tiêu chí, theo thứ tự ưu tiên:
     a. **Đúng chủ đề**, không chỉ trùng từ khoá (snippet lệch nghĩa → loại).
     b. `matched_by` càng nhiều kênh càng đáng tin (`bm25_page` + `bm25_chunk` + `vector_chunk` > 1 kênh).
     c. Trust tier: ưu tiên `verified.by: human:*` > machine-confirmed > unverified.
     d. Trùng chủ đề giữa nhiều page → giữ page canonical (concept, không phải source/index).
   - Chọn **đúng `[retrieval].top_n_final`** page (mặc định 8) để mở. `rerank = "off"` → giữ nguyên thứ tự RRF.
   - Vì sao pool rộng hơn rồi mới cắt: tool xếp hạng bằng tín hiệu thống kê, còn "page này có thật sự trả lời câu hỏi không" cần ngữ nghĩa — đó là phần LLM làm tốt hơn và miễn là không tốn token đọc nhầm file.
4. **Đọc các page đã chọn** (`wiki_read`) để lấy chi tiết + provenance. Đi theo wikilink khi cần mở rộng. Chunk/snippet chỉ để **tìm** concept — không phải nội dung trả lời.
5. Tổng hợp câu trả lời, **cite** nguồn: `[[wiki/<domain>/source/...]]` hoặc URL trong `sources:` — cite Concept path + footnote `[^id]` khi page dùng per-claim citation. KHÔNG trích thẳng chunk thô.
6. **Trust tier check** (áp cả personal + project): page `status: draft` hoặc không có `verified` → gắn cảnh báo "unverified" vào câu trả lời; `stale_after` quá hạn (lint sẽ báo `stale-after-passed`) → cảnh báo stale; ưu tiên human-reviewed (`verified.by: human:*`). Contradiction giữa pages → báo human.
7. Nếu câu hỏi cần synthesis mới (so sánh, connection): **file ngược thành page mới** trong domain phù hợp (`wiki/<domain>/concept/...`) + index tiếp → wiki compounding. Page mới KHÔNG set `verified` — chờ human duyệt qua `llm-wiki verify`.

## Đo chất lượng retrieval

Khi nào chạy `llm-wiki eval`:
- Sau khi bật/tắt `vector`, sau khi đổi `chunk_tokens`/`fusion`, hoặc khi wiki lớn lên rõ rệt.
- `llm-wiki eval --compare` in P@k / R@k / MRR cho 3 profile (`tier1-weighted`, `rrf-text`, `rrf+vector`) → **đó là bằng chứng để bật `vector = true`**, không phải cảm giác.
- Bộ query vàng ở `eval/golden.toml` (commit). Thêm query từ: câu hỏi thật của human trong các phiên, và câu mà wiki trả lời sai (giữ làm regression). `llm-wiki eval --init` tạo file nếu thiếu.
- Kết quả đo append vào `eval/results.json` (gitignored) kèm fingerprint config → so sánh được theo thời gian.
- `zero_recall_queries` trong output = **wiki thiếu kiến thức**, không phải retriever dở → đó là việc của ingest.
- Đọc `matched_by` thấy kênh nào đó biến mất → kiểm tra `chunks_fts` rỗng (`llm-wiki reindex --full`) hoặc lỗi kênh (eval in `[ERROR] kênh bị tắt vì lỗi`).

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
