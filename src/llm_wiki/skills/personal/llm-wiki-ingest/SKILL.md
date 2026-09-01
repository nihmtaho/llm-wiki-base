---
name: llm-wiki-ingest
description: Ingest một raw source vào LLM wiki — auto-detect domain, đọc, tóm tắt, cross-link entity/concept, update index/log, index DB. Dùng khi có source mới trong raw/inbox/.
---

# LLM Wiki — Ingest

Schema: xem `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào
Có source mới trong `raw/inbox/` — do human thả, `scripts/extract_*.py` tạo, HOẶC **AI khác nạp qua MCP `wiki_submit`** (dự án / task / tài liệu). Con người bảo "ingest cái này".

## Quy trình
1. Đọc source: `read_raw_source(name, "inbox", wiki="")` hoặc `wiki_read("raw/inbox/<name>", wiki="")`.
   - Để `wiki=""` để tìm trong all wikis. Nếu biết wiki nguồn, chỉ định `wiki=<name>`.
   - Nếu nội dung mơ hồ / không đủ context để chốt takeaway → `websearch` thêm từ URL/cite trong field `source` của raw (hoặc từ khoá chính trong nội dung) trước khi hỏi human. Không đoán mù.
2. Thảo luận takeaway ngắn với human.
3. **Auto-detect domain** (top-level folder dưới `wiki/`):
   - Đọc content + URL + tiêu đề → xác định chủ đề.
   - **Nếu đã có folder khớp** → dùng luôn.
   - **Nếu chưa có** → tạo folder mới theo naming rule (kebab-case, lowercase, ASCII-safe).
   - **Tạo folder** `wiki/<domain>/` + tạo `wiki/<domain>/index.md` (rỗng, sẽ append ở bước 6).
4. Viết summary page → `wiki/<domain>/source/<slug>.md`.
   - **Frontmatter BẮT BUỘC**: `title`, `domain: <domain>`, `kind: source`, `sources`, `updated`, `status: active`, `generated: {by: "<tool>/<model>", at: <ISO-8601 offset>}`.
   - **KHÔNG set `verified`** — chờ human duyệt artifact (human chạy `llm-wiki verify <path> --by <id>`; áp cả personal + project, xem `_schema.md` Trust tier).
   - **`sources:` khuyến nghị dạng list-of-dicts** + per-claim citation (xem `_schema.md`):
     ```yaml
     sources:
       - id: s1
         resource: <url-hoặc-wiki-xref-hoặc-raw-path>
         title: "..."
     ```
     Body cite claim: `Takeaway quan trọng.[^s1]` + footnote cuối file kèm **trích verbatim** từ raw.
   - Flat list `sources: [<url>]` vẫn hợp lệ (legacy) khi page không cần per-claim citation.
   - **KHÔNG** ghi `raw/inbox/...` vào `sources:`. Inbox là staging, path có thể đổi → drift. `raw/` (ngoài inbox) là local cache do user quản lý, cho phép cite nếu user muốn.
   - **KHÔNG** viết `[[raw/inbox/...]]` trong body — link local chỉ trong `sources:` frontmatter (cho inbox). `[[raw/...]]` (ngoài inbox) cho phép.
5. Tạo/cập nhật entity + concept pages liên quan trong **cùng domain**, cross-link `[[wiki/<domain>/...]]`. 1 source thường chạm 10-15 page.
   - **Chống fork**: trước khi tạo page mới, tra DB (`wiki_list` / `wiki_search`) xem có page `status: planned` cùng chủ đề không → có thì **update**, không create. Page hoàn chỉnh thì `planned → active`.
   - **Pins (`wiki/pins.yml`)**: nếu pin `status: active` bám vào section của page cần sửa → KHÔNG ghi đè section đó. Nguồn mới mâu thuẫn pin → ghi gap vào `wiki/alerts/` (frontmatter `domain: alerts, kind: alert, status: open`), KHÔNG revert âm thầm.
   - **Domain languages:** từ vựng và ngữ pháp trong source phải đưa vào wiki, không chỉ tóm tắt trong source page:
     - Ngữ pháp / mẫu câu → concept page riêng (`wiki/<domain>/concept/<pattern>.md`), 1 pattern = 1 page khi có thể.
     - Từ vựng → gom vào vocab page theo bài/chủ đề (`wiki/<domain>/vocab/<slug>.md`, bảng: từ · đọc · nghĩa · ví dụ) hoặc bổ sung vào entity/concept page có sẵn. Không để từ vựng nằm chết trong source page.
   - **Domain mới:** tạo cả entity/concept/source pages với frontmatter `domain: <name>`, `kind: <role>`.
6. **Auto-translation (nếu enabled)**: đọc `<wiki-root>/.llm-wiki.toml`. Nếu `[translate].enabled = true` và `langs` không rỗng:
   - Với mỗi page vừa tạo (source + entity/concept mới), gọi **skill `llm-wiki-translate`** để dịch sang mỗi lang trong `langs` → tạo `<slug>.<lang>.md` song song.
   - **KHÔNG tự dịch** trong ingest — để skill dùng LLM của AI tool đang chạy.
   - Bản dịch là file parallel, KHÔNG sửa source. Bản dịch tự skip khỏi DB/RAG (rule `*.lang.md`).
   - Nếu `len(langs) > 5` hoặc N pages mới > 20 → cảnh báo user về cost token trước khi gọi skill.
   - Nếu file `.llm-wiki.toml` không tồn tại hoặc `enabled = false` → skip bước này (im lặng).
7. Update `wiki/<domain>/index.md` (thêm entry vào section phù hợp: Entity / Concept / Source / Task). **Nếu domain mới** → thêm row mới vào `wiki/index.md` (top-level) + insert 1 dòng "→ [domain/index.md]" ngay sau header.
8. Insert vào `wiki/log.md` (reverse-chronological: mới nhất trên): `## [YYYY-MM-DD HH:MM:SS] ingest | <title>` + dòng thay đổi.
   - **Ngày = `updated` từ frontmatter của source page vừa viết** (không phải hôm nay). Fallback: `stat -f %Sm` file mtime. Giờ = `date +%H:%M:%S` tại thời điểm ingest để phân biệt cùng ngày.
   - Vị trí: timestamp lớn hơn → chèn trước entry có timestamp nhỏ hơn (gần header nhất). Cùng ngày → so sánh full `YYYY-MM-DD HH:MM:SS`. Dùng `Edit` với anchor là entry kế tiếp để insert chính xác — KHÔNG `Write` rewrite cả file, KHÔNG `cat >>` cuối file.
9. Reindex để search DB + RAG nhận page mới (chạy từ trong wiki dir):
   ```bash
   llm-wiki reindex
   ```
   Mặc định **tăng dần theo content-hash** — chỉ file vừa tạo/sửa được index lại. Bản dịch `*.lang.md` tự skip. KHÔNG qua MCP. Dùng `llm-wiki reindex --check` để dry-run, `--full` khi đổi `chunk_tokens`/`embed_model`/`vector` trong `.llm-wiki.toml`.
10. Move source:
    - Có URL trong `source` field → `mv <wiki_root>/raw/inbox/<name> <wiki_root>/raw/<name>` (local cache, giữ provenance).
    - Không có URL → `mv <wiki_root>/raw/inbox/<name> <wiki_root>/raw/<name>` (local cache, có thể xoá).
11. Verify (chạy từ trong wiki dir):
    ```bash
    llm-wiki reindex
    llm-wiki lint
    ```
    Hoặc tìm page qua MCP `wiki_search`.

## MCP tools (cầu nối cho AI khác)
- Intake: `wiki_submit(title, content, wiki, domain, source)` → ghi vào `raw/inbox/` của wiki `wiki` (bắt buộc chỉ định). AI khác KHÔNG được viết thẳng wiki. `domain` optional, để rỗng = maintainer tự detect ở bước 3.
- Đọc: `read_raw_source` · `wiki_read(path, wiki="")` · `wiki_list(domain=<name>, kind=concept, wiki="")`.
  - `wiki=""` → cross-wiki search. `wiki="<name>"` → target cụ thể.
- Đề xuất (staging): `wiki_propose_edit(path, content, wiki)` (nếu human muốn review trước).
- Index/ingest là việc của maintainer (CLI), KHÔNG qua MCP write.

## An toàn
- Viết wiki pages / index / log là re-derivable → agent tự ghi.
- Mọi claim có provenance (`[[link]]` hoặc URL trong `sources:`).
- Raw immutable — không sửa source.
- **Copied state:** wiki page KHÔNG chứa value move-able (SHA, mtime, count tuyệt đối). Values nằm trong frontmatter hoặc đọc live từ tooling.
