---
name: llm-wiki-ingest
description: >
  Đưa một raw source vào wiki và tích hợp thành concept — auto-detect domain, đọc, tóm tắt,
  cross-link entity/concept, update index/log, reindex tăng dần. Dùng khi có file mới trong
  raw/inbox/ hoặc khi human nói "ingest", "thu nạp nguồn này". Chạy cho cả personal lẫn
  codebase wiki (đọc [wiki].profile).
---

# LLM Wiki — Ingest

Biến nguồn thô thành/cập nhật concept, giữ provenance, không phá nội dung của người, và giữ chỉ mục search đồng bộ ngay.

Schema: `_schema.md`. Runbook: `CLAUDE.md`. Liên quan: `llm-wiki-query` (dùng kiến thức), `llm-wiki-lint` + `llm-wiki-review` (kiểm tra sau), `llm-wiki-reindex` (nếu chỉ cần dựng lại index).

## Profile — đọc trước khi làm

Đọc `[wiki].profile` trong `<wiki_root>/.llm-wiki.toml`:

| | `personal` | `codebase` |
|---|---|---|
| wiki root | thư mục wiki độc lập | `<project>/<wiki-dir>/` (vd `project-wiki/`) |
| 1 source chạm | **10–15 page** (wiki mở rộng theo chủ đề) | **5–10 page** (focused hơn) |
| domain hay dùng | tự do theo chủ đề | `tech-stack`, `architecture`, `conventions`, `dependencies`, `deployment`, `testing`, `security`, `api`, `data-model`, `domain/<sub>` |
| ngôn ngữ nội dung | ngữ pháp/mẫu câu + từ vựng phải vào wiki, không nằm chết trong source page | code path phải **verify** trước khi ghi |

Mark **[personal]** / **[codebase]** dưới đây là phần chỉ áp dụng cho profile đó.

## Khi nào

Có source mới trong `raw/inbox/` — do human thả, `scripts/extract_*.py` tạo, HOẶC **AI khác nạp qua MCP `wiki_submit`** (tài liệu, PR, architecture note, dự án). Con người bảo "ingest cái này".

## Quy trình

1. **Đọc source**: `read_raw_source(name, "inbox", wiki=<tên wiki>)` hoặc `wiki_read("raw/inbox/<name>", wiki=<tên wiki>)`.
   - Tên wiki: `llm-wiki wiki list`. Để `wiki=""` = cross-wiki (chỉ khi thật sự cần tìm nguồn ở wiki khác).
   - Nội dung mơ hồ / không đủ context để chốt takeaway → `websearch` từ URL hoặc cite trong field `source` của raw trước khi hỏi human. **Không đoán mù.**
2. **Thảo luận takeaway ngắn với human** (mặc định ingest từng nguồn một).
3. **Auto-detect domain** (top-level folder dưới `wiki/`):
   - Đọc content + URL + tiêu đề → xác định chủ đề. Đã có folder khớp → dùng luôn.
   - Chưa có → tạo folder mới theo naming rule (kebab-case, lowercase, ASCII-safe) + `wiki/<domain>/index.md` rỗng (append ở bước 7).
   - **[codebase]** Intent (yêu cầu, quyết định) ≠ observation (hành vi đọc được từ code) — đừng trộn một page cả hai; không rõ intent → ghi open question, **không bịa yêu cầu**.
4. **Viết summary page** → `wiki/<domain>/source/<slug>.md`.
   - Frontmatter BẮT BUỘC: `title`, `domain: <domain>`, `kind: source`, `sources`, `updated`, `status: active`, `generated: {by: "<tool>/<model>", at: <ISO-8601 có offset>}`.
   - **KHÔNG set `verified`** — chờ human duyệt artifact (`llm-wiki verify <path> --by <id>`, cùng cơ chế cho cả 2 profile; xem `_schema.md` Trust tier).
   - `sources:` khuyến nghị list-of-dicts + per-claim citation:
     ```yaml
     sources:
       - id: s1
         resource: <url-hoặc-wiki-xref-hoặc-raw-path>
         title: "..."
     ```
     Body cite: `Takeaway quan trọng.[^s1]` + footnote cuối file kèm **trích verbatim** từ raw. Flat list `sources: [<url>]` vẫn hợp lệ (legacy) khi page không cần per-claim citation.
   - Quy tắc `sources:`: có URL gốc → `resource: <url>` (URL là primary provenance); không có URL → source page trong domain là provenance. **KHÔNG** ghi `raw/inbox/...` (staging, đổi path → drift). `raw/` ngoài inbox = local cache, cho phép cite nếu user muốn.
   - **KHÔNG** viết `[[raw/inbox/...]]` trong body — link local chỉ trong `sources:`. `[[raw/...]]` ngoài inbox: cho phép.
   - **[codebase]** Body nên reference code paths khi áp dụng (`src/auth/middleware.ts`, `tests/auth.test.ts`) — inline code hoặc wikilink.
   - **[personal]** Domain languages: ngữ pháp/mẫu câu → concept page riêng (`wiki/<domain>/concept/<pattern>.md`, 1 pattern = 1 page khi có thể); từ vựng → gom vào `wiki/<domain>/vocab/<slug>.md` (bảng: từ · đọc · nghĩa · ví dụ) hoặc bổ sung entity/concept có sẵn.
5. **Tạo/cập nhật entity + concept pages** liên quan trong **cùng domain**, cross-link `[[wiki/<domain>/...]]`.
   - **Chống fork**: trước khi tạo page mới, tra DB (`wiki_list` / `wiki_search`) xem có page `status: planned` cùng chủ đề không → có thì **update**, không create. Page hoàn chỉnh → `planned → active`.
   - **Pins** (`wiki/pins.yml`): pin `status: active` bám vào section của page cần sửa → KHÔNG ghi đè section đó. Nguồn mới mâu thuẫn pin → ghi gap vào `wiki/alerts/` (frontmatter `domain: alerts, kind: alert, status: open`), **không revert âm thầm**.
   - Mỗi page mới phải có ít nhất 1 outbound wikilink (tránh orphan — `llm-wiki-lint` sẽ flag).
   - **[codebase]** kind: `entity` = library/framework/tool/dependency (`wiki/tech-stack/entity/react-query.md`); `concept` = pattern/architecture/layer (`wiki/architecture/concept/middleware-chain.md`); `source` = tóm tắt tài liệu; `task` = task tracking.
6. **Auto-translation (nếu enabled)**: đọc `<wiki_root>/.llm-wiki.toml`. Nếu `[translate].enabled = true` và `langs` không rỗng:
   - Với mỗi page vừa tạo (source + entity/concept mới), gọi **skill `llm-wiki-translate`** → tạo `<slug>.<lang>.md` song song.
   - **KHÔNG tự dịch** trong ingest — để skill translate dùng LLM của AI tool đang chạy.
   - Bản dịch là file parallel, KHÔNG sửa source; tự skip khỏi DB/RAG (rule `*.lang.md`).
   - `len(langs) > 5` hoặc N pages mới > 20 → cảnh báo cost token trước khi gọi skill.
   - Không có `.llm-wiki.toml` hoặc `enabled = false` → skip im lặng.
7. Update `wiki/<domain>/index.md` (thêm entry vào section Entity / Concept / Source / Task). **Domain mới** → thêm row vào `wiki/index.md` (top-level) + insert dòng "→ [domain/index.md]" ngay sau header.
8. Insert vào `wiki/log.md` (reverse-chronological: mới nhất trên): `## [YYYY-MM-DD HH:MM:SS] ingest | <title>` + dòng thay đổi.
   - **Ngày = `updated` từ frontmatter của source page vừa viết** (không phải hôm nay). Fallback: `stat -f %Sm` (macOS) / file mtime. Giờ = `date +%H:%M:%S` tại thời điểm ingest để phân biệt cùng ngày.
   - Vị trí: timestamp lớn hơn → chèn trước entry nhỏ hơn (gần header nhất). Cùng ngày → so full `YYYY-MM-DD HH:MM:SS`.
   - Dùng **Edit với anchor là entry kế tiếp** để insert chính xác — **KHÔNG `Write` rewrite cả file, KHÔNG `cat >>`** (rewrite cả log là mất lịch sử).
9. **Reindex ngay** (tăng dần, chạy từ trong `<wiki_root>`):
   ```bash
   llm-wiki reindex
   ```
   Chỉ file vừa tạo/sửa được index lại (content-hash). Bản dịch `*.lang.md` + `index.md`/`log.md` tự skip khỏi chunk index. `llm-wiki reindex --check` = dry-run; `--full` khi đổi `chunk_tokens`/`embed_model`/`vector`/`fusion`. Chi tiết: skill `llm-wiki-reindex`.
10. **Move source ra khỏi inbox**: `mv <wiki_root>/raw/inbox/<name> <wiki_root>/raw/<name>` — có URL trong `source` thì raw chỉ là local cache gitignored (provenance thật nằm ở URL); không có URL thì đây là bản duy nhất, cân nhắc trước khi để user xoá.
11. **Verify**: `llm-wiki reindex && llm-wiki lint`, hoặc tìm page qua MCP `wiki_search`. Báo cáo: concept đã tạo/sửa, đã reindex gì, và phần nào **cần người duyệt**.

## MCP tools (cầu nối cho AI khác)

- Intake: `wiki_submit(title, content, wiki, domain, source)` → ghi vào `raw/inbox/` của wiki **do human chỉ định**. AI khác KHÔNG được viết thẳng `wiki/`. `domain` optional (để trống = maintainer detect ở bước 3).
- Đọc: `read_raw_source` · `wiki_read(path, wiki)` · `wiki_list(domain=…, kind=concept, wiki)`.
- Đề xuất (staging): `wiki_propose_edit(path, content, wiki)` → `wiki/.proposals/`, chờ `llm-wiki proposals apply|discard`. **Bắt buộc chỉ định `wiki`** khi write.
- **Index/ingest là việc của maintainer qua CLI**, KHÔNG qua MCP write.

## An toàn

- Viết wiki pages / index / log là re-derivable → agent tự ghi. Mọi claim khác phải có provenance (`[[link]]` hoặc URL trong `sources:`).
- **Raw immutable** — không sửa file source. Raw local cache (gitignored) user có thể xoá tùy ý; URL trong `sources:` mới là primary provenance.
- **[codebase] Code path phải verify**: trước khi ghi `src/foo/bar.ts` vào wiki, `grep`/codegraph confirm file tồn tại. Wiki stale về code path là lỗi nghiêm trọng nhất của project wiki.
- **[codebase] Mâu thuẫn wiki ↔ code** → flag human, không tự sửa code lẫn wiki.
- **Copied state**: page KHÔNG chứa value move-able (SHA, mtime, line count, absolute count). Values nằm trong frontmatter hoặc đọc live từ tooling.
- Không set `verified` thay người.
