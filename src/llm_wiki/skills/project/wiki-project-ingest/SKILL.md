---
name: wiki-project-ingest
description: Ingest 1 raw source mới vào project-wiki — auto-detect domain (tech-stack/architecture/convention), viết summary page, cross-link entity/concept, update index/log, index DB. Project-wiki skill — KHÔNG dùng cho personal wiki. Companion của wiki-project-research.
---

# Wiki Project — Ingest

Schema: `_schema.md`. Companion: `wiki-project-research` (research codebase) + `wiki-project-lint` (health-check).

## Khi nào

Có source mới trong `<project>/project-wiki/raw/inbox/` — do human thả, `scripts/extract_*.py` tạo, HOẶC AI khác nạp qua MCP `wiki_submit` (technical doc, PR description, architecture note, etc.).

**KHÔNG dùng skill này cho personal wiki** — chỉ project-wiki tại `<project>/project-wiki/`.

## Quy trình

1. Đọc source: `read_raw_source(name, "inbox", wiki="project-wiki")` hoặc `wiki_read("raw/inbox/<name>", wiki="project-wiki")`.
   - Nếu nội dung mơ hồ / không đủ context → `websearch` thêm từ URL/cite trong frontmatter `source` trước khi hỏi human.
2. Thảo luận takeaway ngắn với human.
3. **Auto-detect domain** (top-level folder dưới `<project>/project-wiki/wiki/`):
   - Đọc content + URL + tiêu đề → xác định chủ đề.
   - Domain thường gặp cho project: `tech-stack`, `architecture`, `conventions`, `dependencies`, `deployment`, `testing`, `security`, `api`, `data-model`, `domain/<sub>`.
   - Nếu đã có folder khớp → dùng luôn. Nếu chưa → tạo folder mới theo naming rule (kebab-case, ASCII-safe).
   - Tạo `wiki/<domain>/index.md` rỗng nếu chưa có.
4. Viết summary page → `wiki/<domain>/source/<slug>.md` với frontmatter BẮT BUỘC: `title`, `domain: <domain>`, `kind: source`, `sources`, `updated`, `status: active`, `confidence: unverified`.
   - **`sources:` field rule**:
     - Có URL gốc (raw có `source: <url>`) → `sources: [<url>]`
     - Không có URL → `sources: []`
     - KHÔNG ghi `raw/inbox/...` (staging, copied-state rule). `raw/` (ngoài inbox) cho phép.
   - **Body nên reference code paths** khi áp dụng: `src/auth/middleware.ts`, `tests/auth.test.ts`, etc. Dùng inline code hoặc wikilink `[[wiki/architecture/...]]`.
5. Tạo/cập nhật entity + concept pages liên quan trong **cùng domain**, cross-link. 1 source thường chạm 5-10 page (project wiki thường focused hơn personal).
   - **Project-specific kinds**:
     - `entity` — library/framework/tool/dependency. VD: `wiki/tech-stack/entity/react-query.md`.
     - `concept` — pattern/architecture/layer. VD: `wiki/architecture/concept/middleware-chain.md`.
     - `source` — raw document summary.
     - `task` — task tracking (nếu dùng).
   - Mỗi page phải có ít nhất 1 outbound wikilink đến page khác (tránh orphan — `wiki-project-lint` sẽ flag).
6. **Auto-translation (nếu enabled)**: đọc `<wiki-root>/.llm-wiki.toml`. Nếu `[translate].enabled = true` và `langs` không rỗng → invoke **skill `llm-wiki-translate`** cho mỗi page vừa tạo (source + entity/concept mới). Bản dịch là file `<slug>.<lang>.md`, skip khỏi DB/RAG.
7. Update `wiki/<domain>/index.md` (thêm entry). Nếu domain mới → thêm row vào `wiki/index.md` (top-level) + insert "→ [domain/index.md]" ngay sau header.
8. Insert vào `wiki/log.md` (reverse-chronological): `## [YYYY-MM-DD HH:MM:SS] ingest | <title>`. Date = `updated` từ source page frontmatter.
9. Reindex (chạy từ trong `<wiki_root>`, vd `<project>/project-wiki/`):
   ```bash
   llm-wiki reindex
   ```
   Idempotent — index `raw/**` + `wiki/**` vào `wiki/.wiki.db` + rebuild `rag/.rag_index/`. Bản dịch `*.lang.md` tự skip.
10. Move source:
    - Có URL trong `source` field → `mv <wiki_root>/raw/inbox/<name> <wiki_root>/raw/<name>` (local cache, giữ provenance).
    - Không có URL → `mv <wiki_root>/raw/inbox/<name> <wiki_root>/raw/<name>` (local cache, có thể xoá).
11. Verify (chạy từ trong `<wiki_root>`):
    ```bash
    llm-wiki reindex
    llm-wiki lint
    ```
    Hoặc tìm page qua MCP `wiki_search`.

## MCP tools (project-wiki)

- Intake: `wiki_submit(title, content, wiki="project-wiki", domain, source)` → ghi vào `raw/inbox/` của project wiki. **Bắt buộc chỉ định `wiki`**. `domain` optional.
- Đọc: `read_raw_source(name, subdir, wiki="project-wiki")` · `wiki_read(path, wiki="project-wiki")` · `wiki_list(domain=<name>, kind=concept, wiki="project-wiki")`.
- Đề xuất: `wiki_propose_edit(path, content, wiki="project-wiki")` — staging vào `wiki/.proposals/`. **Bắt buộc chỉ định `wiki`**.
- Index/ingest là CLI (`tools/reindex.py` + `tools/ingest.py`), KHÔNG qua MCP write.

## An toàn

- Viết wiki pages / index / log là re-derivable → agent tự ghi.
- Mọi claim có provenance: `sources:` URL hoặc wikilink trong body.
- **Code path phải verify**: trước khi ghi `src/foo/bar.ts` vào wiki, nên `grep`/`codegraph` để confirm file thật sự tồn tại. Wiki stale về code path là vấn đề lớn nhất.
- **Contradiction với code** → flag human, không tự sửa.
- **Raw local cache (gitignored).** User có thể xoá tùy ý — provenance nằm trong `sources:` field (URL gốc).
- **Copied state**: page KHÔNG chứa value move-able (SHA, mtime, line count). Cite value chỉ khi claim về quá khứ.
