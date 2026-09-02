---
name: llm-wiki-research
description: >
  Research KIẾN THỨC qua nhiều wiki được chỉ định (không phải trong một wiki duy nhất) —
  cross-wiki search bằng MCP `llm-wiki-base-mcp`, đối chiếu personal ↔ project wiki,
  fallback sang codegraph/grep khi wiki chưa có. Cài ở ROOT của codebase (không nằm trong
  wiki). Dùng khi câu hỏi có thể có câu trả lời ở wiki khác, hoặc khi cần biết máy này có
  wiki nào.
---

# LLM Wiki — Research (cross-wiki)

## Ranh giới với `llm-wiki-query`

| | `llm-wiki-research` (skill này) | `llm-wiki-query` |
|---|---|---|
| phạm vi | **nhiều wiki** được chỉ định, hoặc `wiki=""` = tất cả | **một** wiki bạn đang đứng |
| vị trí cài | `root_project/.agents/skills/` (codebase root) | `<wiki>/.agents/skills/` |
| mục đích | tìm + đối chiếu + decide nguồn nào đáng tin | trả lời + ghi synthesis vào wiki đó |
| write-back | chỉ `wiki_submit` / `wiki_propose_edit` (staging) | được phép ghi page + index + log (maintainer) |

Nếu bạn đã biết câu trả lời nằm ở wiki nào → dùng `llm-wiki-query`, đừng cross-wiki vô ích.

## Server & registry

`llm-wiki-base-mcp` là **một server duy nhất cho cả máy**, đọc `~/.llm-wiki-base/registry.toml` để biết có những wiki nào:

```toml
[[wikis]]
name = "wiki-test"        # key tra cứu — dùng làm tham số `wiki=`
id   = "6f2a…"            # UUID ổn định — không đổi khi bạn đổi tên folder
path = "/Users/…/wiki-test"
type = "personal"         # personal | project
```

```bash
llm-wiki wiki list                      # xem tên + type + path + id
llm-wiki wiki add <name> <path> --type personal
llm-wiki wiki remove <name>
```

**Không có `wiki=` nào trong registry ⇒ MCP không thấy wiki đó.** Wiki chưa đăng ký thì search rỗng, không phải lỗi retriever.

## Khi nào dùng

- Câu hỏi không rõ thuộc wiki nào ("cách tôi đã deploy X", "project này có tiền lệ xử lý Y chưa").
- Cần đối chiếu: project wiki nói A nhưng personal wiki (đọc được qua cross-wiki) đã có quyết định B.
- Before coding trong repo có project wiki: hiểu stack / architecture / convention.
- Cần biết máy này có knowledge base nào để quyết định nơi ghi.

## Quy trình

1. **Liệt kê wiki trước** — `llm-wiki wiki list` (hoặc MCP resource `registry://wikis`). Chọn tập wiki định search; ghi nhớ `type`.
2. **Search**:
   - Đúng 1 wiki → `wiki_search(query, top_k = 2 × top_n_final, wiki="<tên>")`.
   - Nhiều/nghi ngờ → `wiki_search(query, top_k, wiki="")` = cross-wiki; **mỗi kết quả mang field `wiki`** — bắt buộc đọc nó trước khi trích dẫn, nếu không bạn gán nhầm kiến thức cá nhân cho project.
   - Union retrieval: BM25 page ∪ BM25 chunk ∪ vector chunk, gộp bằng **RRF trên hạng**; `vector = false` ở wiki nào → wiki đó tự degrade sang 2 kênh text, vẫn chạy.
3. **Rerank bằng LLM của bạn** khi `[retrieval].rerank = "llm"` (đọc `.llm-wiki.toml` của từng wiki — config là per-wiki): chấm chỉ bằng `title` + `snippet` + `matched_by`, KHÔNG mở file; ưu tiên (a) đúng chủ đề chứ không trùng từ, (b) nhiều kênh cùng bắn ra, (c) `verified.by: human:*`, (d) page canonical (`concept`) thay vì `source`/`index`; rồi cắt xuống `top_n_final`.
4. **Đọc page** (`wiki_read(path, wiki)`) — snippet/chunk chỉ đủ để **chọn** page, không đủ để trả lời. Mở rộng bằng wikilink.
5. **Trust tier + profile check** trước khi tin: `status: draft` / không `verified` → unverified; `stale_after` quá hạn → stale; page của **wiki khác loại** (personal ↔ codebase) → coi là *bối cảnh*, không phải sự thật của repo này.
6. **[fallback] Wiki chưa có → mới tìm code/tech:**
   1. wiki (`wiki_search`/`wiki_read`) — đã curated, có provenance, nhanh;
   2. `codegraph` (nếu cài) — graph call/import, điều hướng tốt hơn grep;
   3. `grep` / `find` — nước cuối.
   **Không nhảy thẳng vào grep khi wiki chưa được check.** Wiki mất công maintain — dùng nó.
7. **Task lớn**: research xong → vào plan mode, cite `[[wiki/<domain>/kind/slug]]` (full path, không bọc wikilink trong markdown link), chỉ rõ gaps, verification phải reproducible. Plan mâu thuẫn wiki → ưu tiên wiki (có provenance), flag conflict. Breaking change → section "Breaking:" riêng.
8. **Không tìm thấy** → nói rõ wiki thiếu gì, rồi đề xuất nạp (xem write-back). Đừng bịa.

## Write-back (chỉ staging — AI proposes, human decides)

| việc | tool | đích |
|---|---|---|
| nạp tài liệu mới | `wiki_submit(title, content, wiki, domain, source)` | `raw/inbox/` của wiki **do human chỉ định** |
| đề xuất sửa page | `wiki_propose_edit(path, content, wiki)` | `wiki/.proposals/` → chờ `llm-wiki proposals apply\|discard` |

- **Bắt buộc chỉ định `wiki` khi write.** Không tự chọn wiki để ghi; không suy ra từ nội dung.
- **MCP không ingest.** Không có tool nào ghi thẳng `wiki/`, `index.md`, `log.md`, và không có tool sửa `.proposals` — duyệt là CLI + người.

## Resources

`registry://wikis` (danh sách wiki), `wiki://<name>/index` (top-level TOC), `wiki://<name>/log` (lịch sử reverse-chronological). Đọc `index` trước khi search khi bạn chưa biết domain của wiki đó.

## An toàn

- **Centralized server, nhiều wiki chung một process.** Kết quả luôn kèm `wiki` + `path`; trích dẫn phải ghi rõ wiki nguồn. Đừng để `wiki=""` khi mục đích chỉ ở một wiki — cross-wiki lẫn kết quả từ wiki cá nhân.
- **Project wiki ≠ personal wiki**, nhưng cross-wiki search cho phép đọc cả hai → hữu ích, và phải phân biệt nguồn.
- **Wiki có thể stale với code** → critical claim phải cross-check code trước khi kết luận.
- **Contradiction** giữa wiki pages / giữa wiki và code → báo human, không tự resolve, không materialize thành "sự thật mới".
- Không đọc `raw/` của wiki người khác làm bằng chứng cho repo này — raw là local cache, có thể bị user xoá; provenance thật là URL trong `sources:`.
