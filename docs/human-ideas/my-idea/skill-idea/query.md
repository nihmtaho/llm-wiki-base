---
name: query
description: >
  Trả lời câu hỏi dựa trên bundle bằng union + hybrid retrieval, có attribution;
  tùy chọn file lại câu trả lời giá trị lâu dài. Kích hoạt khi hỏi về nội dung knowledge base.
---

# Skill: query

Mục tiêu: trả lời chính xác từ wiki đã biên dịch, không nạp thừa, không bịa. RAG chỉ để *tìm* concept, không phải nguồn câu trả lời.

## Quy trình
1. **Đọc `index.md` trước** (progressive disclosure) để định tuyến.
2. **Union retrieval** (đọc `[retrieval]` trong `wiki.config.toml`):
   - **structural**: concept qua `index.md` + đồ thị wikilink.
   - **hybrid**: `BM25(top_k_bm25)` ∪ `vector(top_k_vector)` trên semantic chunk của body (nếu `vector=false` → chỉ BM25).
   - lấy HỢP → khử trùng → **rerank** (`cross-encoder`|`llm`|off) → `top_n_final`.
   - nếu AND-match 0 kết quả và `relax_recall=true` → thử lại OR một lần.
   - thiếu embeddings/rerank → fallback structural + BM25 (vẫn chạy).
3. **Đọc tập concept nhỏ nhất;** đi theo wikilink khi cần mở rộng.
4. **Tổng hợp câu trả lời có attribution** — trích dẫn Concept ID + footnote `sources[].id`.
   **KHÔNG trích thẳng chunk thô làm câu trả lời** — chunk chỉ để tìm concept; nội dung lấy từ concept đã biên dịch (giữ trust tier).
   - Gắn cảnh báo cho `status: draft`/không `verified`/quá `stale_after`; ưu tiên *human-reviewed*.
   - Phân biệt intent (`requirements/`) vs observation (`modules/`) (codebase).
5. **Câu trả lời giá trị lâu dài** → đề xuất file thành concept mới (vd `analysis/…`), `sources` trỏ các concept đã dùng, rồi reindex.
6. **Không tìm thấy** → nói rõ, đề xuất `ingest` hoặc tìm web. Không bịa.

## Không làm
- Không suy diễn ngoài bundle mà không đánh dấu.
- Không trích giá trị hay đổi làm sự thật hiện tại — trỏ về Attested Computation (SCHEMA §7).
