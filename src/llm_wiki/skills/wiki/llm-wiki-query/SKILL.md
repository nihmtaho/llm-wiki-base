---
name: llm-wiki-query
description: >
  Trả lời câu hỏi từ MỘT wiki cụ thể (wiki bạn đang đứng) — union retrieval (BM25 page ∪
  BM25 chunk ∪ vector chunk, RRF) rồi rerank bằng LLM, đọc tập page nhỏ nhất, tổng hợp
  trả lời có cite, và file ngược synthesis thành page mới. Cần tìm qua NHIỀU wiki thì
  dùng skill `llm-wiki-research`.
---

# LLM Wiki — Query

Schema: `_schema.md`. Runbook: `CLAUDE.md`. Liên quan: `llm-wiki-reindex` (index lệch), `llm-wiki-lint` (cấu trúc), `llm-wiki-research` (cross-wiki).

## Ranh giới với `research`

| | `llm-wiki-query` (skill này) | `llm-wiki-research` |
|---|---|---|
| phạm vi | **một** wiki, bạn đã biết wiki nào | nhiều wiki được chỉ định / cross-wiki |
| `wiki=` | tên wiki hiện tại (bỏ trống nếu 1 wiki duy nhất) | `""` hoặc list wiki |
| kết luận | trả lời + có thể **ghi** synthesis vào wiki | so sánh/đối chiếu giữa các nguồn wiki |

## Khi nào

Human đặt câu hỏi về nội dung đã có trong wiki.

## Quy trình

1. **Định tuyến structural**: đọc `wiki/index.md` → domain index (`wiki/<domain>/index.md`). Route tốt nhất khi đã biết domain; bỏ qua nếu không rõ.
   - **[codebase]** Nếu đang ở root của repo có project wiki, đọc `<wiki_root>/wiki/index.md` để biết domain (tech-stack, architecture, conventions, …).
2. **Lấy pool ứng viên RỘNG hơn số cần đọc**:
   - `wiki_search(query, top_k = 2 × [retrieval].top_n_final, wiki=<tên wiki>)` — union retrieval: BM25 page ∪ BM25 chunk ∪ vector chunk, gộp bằng **RRF trên hạng**. Đọc `[retrieval]` trong `.llm-wiki.toml`.
   - Query tiếng Việt / ký tự đặc biệt: tool tự nới (giữ nguyên → AND sanitize → OR) khi `relax_recall = true`.
   - `semantic_search(query, top_k, wiki)` khi cần xem riêng kênh vector chunk (chỉ có khi `vector = true`).
   - Filter: `wiki_list(domain="…", kind="concept", wiki=…)`.
3. **RERANK ở bước này (skill làm, không phải tool)** — khi `[retrieval].rerank = "llm"`:
   - Chỉ dùng `title` + `snippet` + `matched_by` của mỗi ứng viên; **KHÔNG mở file** lúc chấm.
   - Tiêu chí, theo thứ tự ưu tiên:
     a. **Đúng chủ đề**, không chỉ trùng từ khoá (snippet lệch nghĩa → loại).
     b. `matched_by` càng nhiều kênh càng đáng tin (`bm25_page` + `bm25_chunk` + `vector_chunk` > 1 kênh).
     c. Trust tier: ưu tiên `verified.by: human:*` > machine-confirmed > unverified.
     d. Trùng chủ đề giữa nhiều page → giữ page canonical (`concept`, không phải `source`/`index`).
   - Chọn **đúng `[retrieval].top_n_final`** page (mặc định 8) để mở. `rerank = "off"` → giữ nguyên thứ tự RRF.
   - Vì sao pool rộng rồi mới cắt: tool xếp hạng bằng tín hiệu thống kê, còn "page này có thật sự trả lời không" cần ngữ nghĩa — phần đó LLM làm tốt hơn, miễn là đừng tốn token đọc nhầm file.
4. **Đọc các page đã chọn** (`wiki_read`) để lấy chi tiết + provenance. Đi theo wikilink khi cần mở rộng. **Chunk/snippet chỉ để *tìm* concept — không phải nội dung trả lời**; câu trả lời lấy từ page đã biên dịch (giữ trust tier).
5. **Tổng hợp câu trả lời, có cite**: `[[wiki/<domain>/source/...]]` hoặc URL trong `sources:`; cite Concept path + footnote `[^id]` khi page dùng per-claim citation.
   - **[codebase]** Phân biệt intent (`requirements`/quyết định) vs observation (hành vi đọc từ code) — đừng trả observation như thể đó là yêu cầu.
6. **Trust tier check** (cả 2 profile): `status: draft` hoặc không có `verified` → gắn cảnh báo "unverified" vào câu trả lời; `stale_after` quá hạn (lint báo `stale-after-passed`) → cảnh báo stale; ưu tiên human-reviewed.
   - **[codebase]** Wiki **có thể stale với code**: critical claim phải cross-check bằng `grep`/codegraph trước khi kết luận. Thứ tự ưu tiên nguồn: wiki → codegraph → grep/find. **Không nhảy thẳng vào grep khi wiki chưa được check** — wiki mất công maintain, dùng nó.
   - Contradiction giữa pages (hoặc giữa wiki và code) → **báo human**, không tự resolve, không ghi edge.
7. Nếu câu hỏi cần synthesis mới (so sánh, connection): **file ngược thành page mới** trong domain phù hợp (`wiki/<domain>/concept/...`) + cập nhật index → wiki compounding. Page mới KHÔNG set `verified` — chờ `llm-wiki verify`.
   - **[codebase]** Nếu chỉ được phép đề xuất (không phải maintainer): dùng `wiki_propose_edit` → staging `.proposals/`, chờ `llm-wiki proposals apply`.
8. Không tìm thấy → nói rõ, đề xuất ingest (`wiki_submit` vào `raw/inbox/`) hoặc tìm web. **Không bịa.**

## Task lớn: research rồi mới plan

Trước khi refactor / feature mới / multi-file change: chạy quy trình trên để lấy context, **rồi** vào plan mode (Shift+Tab), cite wiki pages trong plan, chỉ ra gaps, và liệt kê page cần update sau khi implement. Mỗi claim quan trọng trong plan phải có wiki path hoặc URL; verification phải reproducible (MCP tool hoặc shell command, không "test thử"). Nếu plan mâu thuẫn wiki → ưu tiên wiki (đã có provenance), flag conflict cho human. Breaking change → section "Breaking:" riêng.

## Đo chất lượng retrieval

Chạy `llm-wiki eval` khi: bật/tắt `vector`, đổi `chunk_tokens`/`fusion`, hoặc wiki lớn lên rõ rệt.

```bash
llm-wiki eval            # P@k / R@k / MRR theo config hiện tại
llm-wiki eval --compare  # so tier1-weighted / rrf-text / rrf+vector + verdict
llm-wiki eval --init     # tạo eval/golden.toml từ template
```

- `--compare` là **bằng chứng** để bật `vector = true`, không phải cảm giác.
- Query vàng ở `eval/golden.toml` (commit). Lấy từ: câu hỏi thật của human trong các phiên, và câu mà wiki trả lời sai (giữ làm regression). **Đừng để AI tự soạn query hộ** — số liệu khi đó đo cái wiki trùng ý AI, không đo usage thật.
- Kết quả append `eval/results.json` (gitignored) kèm fingerprint config → so được theo thời gian.
- `zero_recall_queries` = **wiki thiếu kiến thức**, không phải retriever dở → việc của `llm-wiki-ingest`.
- Thấy kênh biến mất trong `matched_by` → check `chunks_fts` rỗng (`llm-wiki reindex --full`) hoặc lỗi kênh (eval in `[ERROR] kênh bị tắt vì lỗi`).

## MCP tools

Centralized server `llm-wiki-base-mcp` — mỗi tool có param `wiki=`:
`wiki_search(query, top_k, wiki)` · `semantic_search(query, top_k, wiki)` · `wiki_read(path, wiki)` · `wiki_list(domain, kind, wiki)` · `wiki_lint(wiki)`.
Kết quả search/read luôn mang field `wiki` để biết nguồn gốc.

## An toàn

- Không bịa claim không có trong wiki/raw; không suy diễn ngoài wiki mà không đánh dấu.
- Không trích value hay đổi làm sự thật hiện tại (SHA, mtime, count) — trỏ về nguồn live.
- Cross-domain synthesis: page trải nhiều domain → đặt vào domain user quan tâm nhất, hoặc tạo domain mới.
- `wiki_submit` là cổng nạp của **AI khác**, không phải của bạn khi đang maintain.
