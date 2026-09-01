---
name: llm-wiki-ingest
description: Ingest một raw source vào LLM wiki — auto-detect domain, đọc, tóm tắt, cross-link entity/concept, update index/log, index DB. Dùng khi có source mới trong raw/inbox/.
---

# LLM Wiki — Ingest

Schema: xem `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào
Có source mới trong `raw/inbox/` — do human thả, `scripts/extract_*.py` tạo, HOẶC **AI khác nạp qua MCP `wiki_submit`** (dự án / task / tài liệu). Con người bảo "ingest cái này".

## Quy trình
1. Đọc source: `read_raw_source(name, "inbox")` hoặc `wiki_read("raw/inbox/<name>")`.
   - Nếu nội dung mơ hồ / không đủ context để chốt takeaway → `websearch` thêm từ URL/cite trong field `source` của raw (hoặc từ khoá chính trong nội dung) trước khi hỏi human. Không đoán mù.
2. Thảo luận takeaway ngắn với human.
3. **Auto-detect domain** (top-level folder dưới `wiki/`):
   - Đọc content + URL + tiêu đề → xác định chủ đề.
   - **Nếu đã có folder khớp** → dùng luôn.
   - **Nếu chưa có** → tạo folder mới theo naming rule (kebab-case, lowercase, ASCII-safe).
   - **Tạo folder** `wiki/<domain>/` + tạo `wiki/<domain>/index.md` (rỗng, sẽ append ở bước 6).
4. Viết summary page → `wiki/<domain>/source/<slug>.md`.
   - **Frontmatter BẮT BUỘC**: `title`, `domain: <domain>`, `kind: source`, `sources`, `updated`, `status: active`. Khuyến nghị `confidence: unverified` (mặc định).
   - **`sources:` field rule** (xem `_schema.md`):
     - Có URL gốc (raw file có `source: <url>`) → `sources: [<url>]` (hoặc nhiều URL)
     - Không có URL gốc → `sources: []`. Source page trong domain là immutable gốc, không cần cite lại `raw/inbox/<name>` hay `archived/<name>` (copied-state rule).
     - Concept/entity page tổng hợp từ nhiều source → `sources: [wiki/<domain>/source/<other>.md, ...]`
     - **KHÔNG** ghi `raw/...` / `archived/...` / `inbox/...` vào `sources:`. File intermediate ở `raw/inbox/` rồi sẽ move sang `raw/` hoặc `archived/`, path có thể đổi → drift.
     - **KHÔNG** viết `[[raw/...]]` / `[[archived/...]]` trong body — link local chỉ trong `sources:` frontmatter.
5. Tạo/cập nhật entity + concept pages liên quan trong **cùng domain**, cross-link `[[wiki/<domain>/...]]`. 1 source thường chạm 10-15 page.
   - **Domain languages:** từ vựng và ngữ pháp trong source phải đưa vào wiki, không chỉ tóm tắt trong source page:
     - Ngữ pháp / mẫu câu → concept page riêng (`wiki/<domain>/concept/<pattern>.md`), 1 pattern = 1 page khi có thể.
     - Từ vựng → gom vào vocab page theo bài/chủ đề (`wiki/<domain>/vocab/<slug>.md`, bảng: từ · đọc · nghĩa · ví dụ) hoặc bổ sung vào entity/concept page có sẵn. Không để từ vựng nằm chết trong source page.
   - **Domain mới:** tạo cả entity/concept/source pages với frontmatter `domain: <name>`, `kind: <role>`.
6. Update `wiki/<domain>/index.md` (thêm entry vào section phù hợp: Entity / Concept / Source / Task). **Nếu domain mới** → thêm row mới vào `wiki/index.md` (top-level) + insert 1 dòng "→ [domain/index.md]" ngay sau header.
7. Insert vào `wiki/log.md` (reverse-chronological: mới nhất trên): `## [YYYY-MM-DD HH:MM:SS] ingest | <title>` + dòng thay đổi.
   - **Ngày = `updated` từ frontmatter của source page vừa viết** (không phải hôm nay). Fallback: `stat -f %Sm` file mtime. Giờ = `date +%H:%M:%S` tại thời điểm ingest để phân biệt cùng ngày.
   - Vị trí: timestamp lớn hơn → chèn trước entry có timestamp nhỏ hơn (gần header nhất). Cùng ngày → so sánh full `YYYY-MM-DD HH:MM:SS`. Dùng `Edit` với anchor là entry kế tiếp để insert chính xác — KHÔNG `Write` rewrite cả file, KHÔNG `cat >>` cuối file.
8. Reindex để search DB + rag nhận page mới (chỉ maintainer, CLI): `.venv/bin/python tools/reindex.py`. Lệnh index `raw/**` + `wiki/**` vào `wiki/.wiki.db` và rebuild `rag/.rag_index/`. KHÔNG qua MCP.
9. Move source:
   - Có URL trong `source` field → `mv raw/inbox/<name> raw/<name>` (immutable, giữ provenance).
   - Không có URL → `mv raw/inbox/<name> archived/<name>` (archived, immutable).
10. Verify: `.venv/bin/python -c "import db,search; from embed import EmbedProvider; print(search.hybrid_search(db.get_conn(),'<từ khoá>',provider=EmbedProvider())[:3])"` phải trả page mới với `domain=<domain>` trong result.

## MCP tools (cầu nối cho AI khác)
- Intake: `wiki_submit(title, content, domain, source)` → ghi vào `raw/inbox/` (AI khác KHÔNG được viết thẳng wiki). `domain` optional, để rỗng = maintainer tự detect ở bước 3.
- Đọc: `read_raw_source` · `wiki_read` · `wiki_list(domain=<name>, kind=concept)`.
- Đề xuất (staging): `wiki_propose_edit` (nếu human muốn review trước).
- Index/ingest là việc của maintainer (CLI), KHÔNG qua MCP write.

## An toàn
- Viết wiki pages / index / log là re-derivable → agent tự ghi.
- Mọi claim có provenance (`[[link]]` hoặc URL trong `sources:`).
- Raw immutable — không sửa source.
- **Copied state:** wiki page KHÔNG chứa value move-able (SHA, mtime, count tuyệt đối). Values nằm trong frontmatter hoặc đọc live từ tooling.
