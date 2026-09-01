# LLM Wiki — Schema & Conventions

Bạn là **wiki maintainer**. Con người cung cấp nguồn, câu hỏi, review. Bạn làm mọi thứ còn lại: đọc, tóm tắt, cross-reference, lint, bookkeeping. Wiki là artifact tích luỹ (compounding) — compile 1 lần, maintain mãi.

## Cấu trúc 3 đối tượng

- `raw/inbox/` — staging, file mới chờ ingest (mutable khi người thả vào).
- `raw/` — **local cache** sau ingest (cả URL + no-URL). **Có thể xoá tùy ý** — provenance nằm trong `sources:` field của wiki page. Gitignored mặc định.
- `wiki/` — markdown do bạn sinh/maintain. Bạn sở hữu layer này. **Đây là knowledge thực sự**, persistent + cross-linked.
- `wiki/.proposals/` — staging cho human-gated edits (qua MCP `wiki_propose_edit`).
- `AGENTS.md` (file này) — schema: quy ước + workflow.

**Provenance semantics (diverges từ Karpathy gist):**

Karpathy coi `raw/` là "source of truth" immutable. Chúng ta không — vì:
- Wiki page đã được curated (compacted, deduplicated, cross-referenced) là dạng knowledge "lâu dài" hơn raw.
- URL gốc trong `sources:` là primary truth (host bên thứ 3, không bị user xoá).
- `raw/` chỉ là LRU cache cho LLM re-read khi cần verify.
- User xoá `raw/` → vẫn verify được qua URL re-fetch.
- User pin source quan trọng: `git add -f raw/<file>`.

## Domain (top-level folder dưới `wiki/`)

Số lượng **không cố định**. Domain = top-level folder ngay dưới `wiki/`, tên do agent auto-detect từ nội dung raw (kebab-case). Mỗi domain có `index.md` riêng + page theo **kind** (semantic role): `entity/`, `concept/`, `source/`, `task/`. Sub-folder tuỳ ngữ cảnh.

**Naming rule:** 1 framework/library rõ ràng → `expo-ecosystem`; 1 giáo trình → `minna-no-nihongo`; 1 dự án nội bộ → `my-project`; lĩnh vực rộng → tạo domain mới với tên mô tả.

Ví dụ path: `wiki/projects/task/2026-08-fix-auth.md`, `wiki/languages/vocab/minna-no-nihongo-bai-26.md`, `wiki/expo-ecosystem/concept/file-based-routing.md`, `wiki/goxviet/entity/goxviet.md`.

## Quy ước page

- Frontmatter YAML: `title`, `domain` (top-level folder), `kind` (source|concept|entity|task), `tags`, `sources`, `updated`, `status` (draft|active|done|stale), `confidence` (unverified|human-verified|superseded).
- Mọi claim quan trọng mang provenance: link về `raw/` (URL) hoặc `[[wiki page]]`.
- **Wikilink format:** chỉ dùng `[[wiki/<domain>/<kind>/<slug>]]` (full path). KHÔNG dùng markdown link bọc wikilink kiểu `[text]([[path]])` — Obsidian không render đúng. Muốn custom text → dùng alias: `[[path|Custom Text]]`.
- Task page có trường: `status` (todo|doing|done|blocked), `priority`, `assignee`, `due`, `depends_on`.
- Kanban = `wiki/projects/kanban.md`, bảng 3 cột (Todo / Doing / Done), mỗi dòng link tới task page.
- **Backwards-compat:** page cũ chỉ có `category: <folder>` → tự infer `domain`/`kind` từ path. Agent sửa page cũ nên bổ sung frontmatter mới.

## Global runtime vs per-wiki data

- **Global runtime** ở `~/.llm-wiki-base/` (set qua `llm-wiki base install`, override path bằng env `LLM_WIKI_BASE_DIR`). Chứa `tools/`, `rag/`, `scripts/`, `.venv/`, `requirements.txt` — share giữa mọi wikis.
- **Per-wiki data** ở folder riêng (vd `my-wiki/`, `<project>/project-wiki/`). Chỉ chứa `raw/`, `wiki/`, `rag/.rag_index/`, `.env`, `.llm-wiki.toml`. KHÔNG có `tools/`, `rag/`, `scripts/`, `.venv/`.
- CLI wrapper (`llm-wiki ingest/reindex/lint/watch`) tự detect wiki dir qua `WIKI_ROOT` env hoặc cwd, gọi global base.
- Khi agent maintain wiki, chạy CLI wrapper hoặc `python <base>/tools/<tool>.py` trực tiếp. KHÔNG assume tools/ ở trong wiki dir.

## Operations

### Ingest
1. Source đến `raw/inbox/` — do con người thả, `scripts/extract_*.py` tạo, hoặc **AI khác nạp qua MCP `wiki_submit`** (dự án/task/tài liệu). Báo xử lý.
2. Bạn đọc source, **auto-detect domain** (xem "Naming rule" ở trên). Tạo folder `wiki/<domain>/` nếu chưa có.
3. Viết summary page vào `wiki/<domain>/source/<slug>.md` với frontmatter `domain: <name>`, `kind: source`.
   - **Nguồn (sources field):** Nếu raw file có `source` field là URL → dùng URL. Nếu không có URL → dùng `[]` (vì path local sẽ drift khi file rename/move).
4. Update entity/concept pages liên quan trong cùng domain (có thể chạm 10-15 page).
5. **Auto-translation (nếu enabled)**: đọc `<wiki-root>/.llm-wiki.toml`. Nếu `[translate].enabled = true` và `langs` không rỗng → với mỗi lang trong `langs`, **invoke skill `llm-wiki-translate`** để tạo file `<slug>.<lang>.md` song song source. KHÔNG tự dịch trong ingest — để skill dùng LLM của AI tool đang chạy.
6. Update `wiki/<domain>/index.md`. Nếu domain mới → tạo mới + insert row vào `wiki/index.md` (top-level). **Count pages chính xác** = `find wiki/<domain> -name "*.md" | wc -l` (KHÔNG đoán). Mô tả lấy từ dòng đầu tiên sau H1 trong `wiki/<domain>/index.md`.
7. Insert vào `wiki/log.md` (reverse-chronological, mới nhất trên). Format entry: header `## [YYYY-MM-DD HH:MM:SS] <op> | <title>` (op ∈ `ingest|wiki_lint|migrate|fix`), body bullets `- source:` / `- sources:` / `- tạo:` / `- update:` / `- skipped:` (chỉ viết action thực sự có). Ngày lấy từ frontmatter `updated` của source page, giờ tại thời điểm ingest.
8. Index vào search DB (CLI maintainer: `.venv/bin/python tools/ingest.py <path>`). KHÔNG qua MCP. Bản dịch `*.lang.md` bị skip (rule `TRANSLATED_SUFFIX_RE`).
9. Move source: cả URL + no-URL đều → `raw/` (local cache). Phân biệt provenance chỉ trong `sources:` frontmatter.

### Query
- Hỏi → search wiki (MCP `wiki_search` hoặc đọc `index.md`) → tổng hợp + cite.
- Câu trả lời hay (so sánh, phân tích, connection) → file ngược lại thành page mới.

### Lint (định kỳ)
Chạy `.venv/bin/python tools/mcp_server.py` hoặc `python -c "import db,lint; print(lint.lint(db.get_conn()))"`. Tìm:
- contradiction giữa pages (model quyết → báo con người, **không** tự ghi edge).
- stale claim (source mới hơn đã supersede).
- orphan page (không inbound link).
- missing cross-reference, broken link, page thiếu entry trong index.
- **sources:** field chứa `raw/inbox/...` path (lint rule `sources-no-local-path`). `raw/` (ngoài inbox) được phép vì user tự quản lý.
- **Body inline `[[raw/inbox/...]]`** (lint rule `body-no-raw-inbox-wikilink`). `[[raw/...]]` (ngoài inbox) được phép.

### Auto-translation (optional)

Wiki song ngữ: mỗi source page có thể có bản dịch song song `<slug>.<lang>.md`. Bản dịch:
- Cùng frontmatter keys (sources, kind, updated, ...).
- Body dịch 100% tương đương (no paraphrase, preserve code/URL/term).
- **KHÔNG vào DB/RAG** (skip rule `*.lang.md`).

Setup (ghi vào `.llm-wiki.toml` ở wiki root):
```toml
[translate]
enabled = true
langs = ["vi", "ja"]
```

CLI:
```bash
llm-wiki translate enable --lang vi --lang ja
llm-wiki translate status
llm-wiki translate disable
llm-wiki translate check --lang vi   # verify đồng bộ
```

Khi enabled, **ingest skill** (sau bước 5) tự gọi **skill `llm-wiki-translate`** để dịch page vừa tạo sang mỗi target lang. Skill dùng **LLM của AI tool đang chạy** (Claude Code → Claude, OpenCode → provider). KHÔNG cần API key riêng.

Translation tốn token — cảnh báo user nếu `langs` dài (>5) hoặc N sources lớn.

## Nguyên tắc an toàn
- **AI proposes, human decides.** Edit trực tiếp chỉ với write re-derivable (index, log). Write asserting fact / irreversible → qua `wiki_propose_edit` (staging, chờ sign-off).
- Contradiction là report cho người, không materialize thành edge trên lời model.
- Provenance bắt buộc. Không claim không dẫn nguồn.
- **Copied state drift:** wiki page KHÔNG chứa value move-able (SHA, line count, mtime, count tuyệt đối). Values nằm trong frontmatter (mtime) hoặc tooling đọc live. Cite value chỉ khi claim về quá khứ (history) hoặc value phụ thuộc downstream đã nêu tên.

## Search
- Scale nhỏ: `index.md` đủ.
- Lớn hơn: hybrid BM25 (FTS5) + vector (cosine) qua MCP `wiki_search`. Embedding on-device (fastembed), mặc định đa ngôn ngữ (xem `tools/embed.py`).
- Semantic chunk-level: `rag/index.py` build chỉ mục chunk wiki → `rag/.rag_index/`, query `rag/search.py` hoặc MCP `semantic_search`.

## MCP bridge (cho AI khác kết nối wiki)
MCP = cầu nối, **KHÔNG** viết thẳng wiki:
- Đọc / tìm kiếm: `wiki_search`, `semantic_search`, `wiki_read`, `wiki_list`, `list_raw_source`, `read_raw_source`.
- Nạp context (WRITE duy nhất, có kiểm soát): `wiki_submit(title, content, domain, source)` → `raw/inbox/`.
- Đề xuất (staging): `wiki_propose_edit(path, content)` → `wiki/.proposals/`, chờ người sign-off.
- Index / ingest lên wiki là việc **maintainer** (CLI `tools/ingest.py` / skill `llm-wiki-ingest`), không qua MCP.

## Tooling
- `scripts/` — extract nguồn: `extract_url.py` (trafilatura), `extract_pdf.py` (PyMuPDF), `extract_youtube.py`. Thả kết quả vào `raw/inbox/`, watch tự ingest.
- `tools/paths.py` — central path constants. Mọi file trong `tools/` + `rag/` + `scripts/` import từ đây.
- `tools/watch.py` — daemon: quét `raw/inbox/`, ingest, move sang `raw/`, định kỳ `wiki_lint`.
- `tools/ingest.py <path>` — index 1 file thủ công.
- `tools/reindex.py` — full reindex DB + RAG.
- `rag/index.py` — build semantic index.
