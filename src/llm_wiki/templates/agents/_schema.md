# Schema & Conventions

Wiki là artifact tích luỹ do LLM maintain. Compile 1 lần, giữ current.

## 3 đối tượng trong data flow

- `raw/inbox/` — staging. File mới chờ ingest. Mutable khi người/AI thả vào.
- `raw/` — **local cache** sau ingest (cả URL + no-URL). **Có thể xoá tùy ý** — provenance nằm trong `sources:` field của wiki page. Gitignored mặc định.
- `wiki/` — markdown do LLM sinh/maintain. LLM sở hữu layer này. **Đây là knowledge thực sự** (curated, cross-linked, persistent).
- `AGENTS.md` / `CLAUDE.md` — schema: quy ước + workflow vận hành.

Move rules:
- Source có URL HOẶC không có URL → đều move từ `raw/inbox/` sang `raw/`. Phân biệt provenance chỉ trong `sources:` field (URL = strong, `[]` = weak).
- `raw/inbox/` là staging only — files ở đây chưa ingest.
- `raw/` (ngoài inbox) là local cache. User có thể xoá tùy ý; nếu cần backup thủ công, dùng `git add -f raw/<file>`.
- Body text không bao giờ link inline `[[raw/inbox/...]]` — chỉ `sources:` field được phép (xem rule 4 dưới). `[[raw/...]]` (ngoài inbox) được phép vì user tự quản lý.

## Domain (top-level folder dưới `wiki/`)

**Domain = top-level folder ngay dưới `wiki/`** — số lượng **không cố định**. Tên folder do agent auto-detect từ nội dung raw + tiêu đề + URL.

**Naming rule cho domain mới** (agent dùng khi auto-create):
- 1 framework/library rõ ràng → kebab-case tên (`expo-ecosystem`, `react-navigation`, `claude-code`).
- 1 giáo trình / series → kebab-case tên series (`minna-no-nihongo`).
- 1 dự án nội bộ → kebab-case tên project (`my-project`).
- Lĩnh vực rộng chưa rõ project → tạo mới với tên mô tả (vd: `distributed-systems`).
- Lowercase, kebab-case, ASCII-safe.

## Cấu trúc bên trong mỗi domain

Mỗi domain folder có `index.md` riêng + page theo **kind** (semantic role):
- `entity/` — thực thể (framework, người, tổ chức, library, tool).
- `concept/` — khái niệm / pattern / lý thuyết.
- `source/` — summary của raw source.
- `task/` — chỉ domain có task tracking.
- Sub-folder tuỳ ngữ cảnh: `vocab/` (languages), `analysis/`, `comparison/`...

## Quy ước page

Frontmatter YAML:
```yaml
title: ...
domain: <tên folder top-level>
kind: source|concept|entity|task|alert
tags: [...]
sources: ...                      # provenance — 2 dạng, xem rule dưới
updated: YYYY-MM-DD
status: draft|active|done|stale|planned|deprecated|superseded
confidence: unverified|human-verified|machine-confirmed|superseded   # legacy
# --- trust fields (optional, khuyến nghị cho page mới) ---
generated: {by: "<tool>/<model>", at: 2026-09-01T09:00:00+07:00}
verified:  {by: "human:<id>",     at: 2026-09-01T10:00:00+07:00}  # vắng = unverified
stale_after: 2027-01-01T00:00:00+07:00   # quá hạn → lint báo stale-after-passed
x_owner: "human:<id>"
x_supersedes: wiki/<domain>/concept/<old>   # khi status: superseded
```

**`sources:` field rule:**

`sources:` chấp nhận **2 dạng** (dual-format — flat list vẫn valid cho page cũ):

- **Flat list (legacy)**: `sources: [<url>...] | [<wiki-xref>...] | []`
- **List-of-dicts (khuyến nghị page mới)** — per-claim citation qua footnote:
```yaml
sources:
  - id: s1
    resource: https://example.com/api/     # URL hoặc wiki-xref hoặc raw/ path
    title: "API docs"
```
  Body cite từng claim: `Claim quan trọng.[^s1]` + footnote cuối file kèm trích verbatim:
  ```
  [^s1]: API docs
      > [human:<id>] "prod phải là Postgres, SQLite chỉ để test local"
  ```
  Lint check `footnote-sources-match`: mọi `[^id]` phải khớp `sources[].id` và ngược lại.
  **Distill-verify**: khi merge/consolidate, citation set của page KHÔNG được co lại.

Quy tắc chung (áp cả 2 dạng):
1. **URL gốc** nếu raw file có `source: <url>` (docs/blog/GitHub) — provenance mạnh nhất. Nhiều URL OK.
2. **Wiki cross-link** `[[wiki/<domain>/source/<other>]]` nếu claim dựa trên 1 source page khác trong wiki.
3. **`sources: []`** khi page không có URL gốc (task intake, log nội bộ, bài viết cá nhân) HOẶC khi `raw/` file là intermediate (đã move ra khỏi `raw/inbox/`).
4. **KHÔNG** ghi `raw/inbox/...` vào `sources:` — đó là staging, vi phạm copied-state rule (path local có thể rename/move trong khi wiki page vẫn trỏ tới path cũ). `raw/` (ngoài inbox) cho phép cite vì user tự quyết việc commit/backup.
5. **KHÔNG** link tới `raw/inbox/` trong body text — chỉ trong `sources:` field. `[[raw/...]]` (ngoài inbox) cho phép — user tự quyết.

Ví dụ hợp lệ:
```yaml
sources: [https://docs.example.com/api/]
sources: [https://docs.example.com/api/, https://github.com/foo/bar]
sources: [wiki/<domain>/source/<other>.md]
sources: [https://docs.example.com/api/, wiki/<domain>/source/<other>.md]
sources: []
```

- Mọi claim quan trọng mang provenance: link `[[wiki page]]` trong body hoặc URL trong `sources:`.
- Task page thêm: `status` (todo|doing|done|blocked), `priority`, `assignee`, `due`, `depends_on`.
- Kanban = `wiki/projects/kanban.md`, 3 cột (Todo / Doing / Done), mỗi dòng link task page.

**Backwards-compat:** page cũ chỉ có `category: <folder>` (không có `domain`/`kind`) → tự động infer từ path.

## Trust tier & verify (cả personal + project)

- **unverified** — không có `verified` (mặc định khi AI viết; `generated` ghi ai sinh, lúc nào).
- **machine-confirmed** — `verified.by` là agent (check tất định qua máy).
- **human-reviewed** — `verified.by` = `human:<id>`. Chỉ tier này mới là canonical cho JUDGMENT.

**Duyệt artifact = set `verified`** qua lệnh (dùng chung cho cả personal + project wiki):

```bash
llm-wiki verify wiki/<domain>/concept/<slug>.md --by <human-id>   # set verified → human-reviewed
llm-wiki verify <path> --unverify                                 # xoá verified (hạ về unverified)
```

AI KHÔNG tự set `verified`. Consolidate/review đổi nội dung judgment → `--unverify` phần đó, chờ human duyệt lại.

## Chống fork — status: planned

Trước khi tạo page mới, tra DB page `status: planned` cùng slug: có → **update**, không create.
Reserve = tạo placeholder `status: planned` trước khi sinh nội dung; ingest sau thấy planned → điền nội dung + `status: active`. Không cần file registry riêng.

## Pins — wiki/pins.yml (sửa tay của human, sống sót qua regenerate)

```yaml
- concept: wiki/<domain>/concept/<slug>
  kind: correction            # correction | addition | deletion
  claim: "Nội dung human muốn giữ"
  anchor: "## <heading>"      # section mà pin bám vào
  provenance: "human:<id>"
  status: active
```

- Ingest/consolidate KHÔNG ghi đè section mà pin `active` bám vào.
- Nguồn mới mâu thuẫn pin → đẩy vào `wiki/alerts/`, KHÔNG revert âm thầm.
- Lint check `pin-orphan`: anchor heading mất / concept không tồn tại → report human (không tự xoá pin).

## Alerts — wiki/alerts/ (hàng đợi gap)

- Gap từ review skill (mâu thuẫn, stale, trust gap, pin conflict) ghi thành page:
  frontmatter `domain: alerts, kind: alert, status: open, last_seen: <date>`.
- Gap không bị nêu lại 2 lần chạy review liên tiếp → `status: closed` (tự đóng).
- Là pseudo-domain: vẫn có `wiki/alerts/index.md`, vẫn vào DB/search.

## Operations

### Ingest
1. Con người thả source vào `raw/inbox/` (hoặc AI khác qua MCP `wiki_submit`).
2. LLM đọc, **auto-detect domain**, thảo luận takeaway.
3. Viết summary → `wiki/<domain>/source/<slug>.md` với frontmatter `domain: <domain>`, `kind: source`.
4. Update entity/concept pages liên quan trong cùng domain.
5. Update `wiki/<domain>/index.md`. Nếu domain mới → tạo file mới + insert row vào `wiki/index.md`.
6. Insert vào `wiki/log.md` (reverse-chronological, mới nhất trên).
7. Index vào search DB (`tools/ingest.py`).
8. Move source: cả URL + no-URL đều → `raw/` (local cache). Phân biệt provenance chỉ trong `sources:` frontmatter.

### Query
- Hỏi → search wiki (MCP `wiki_search` / `semantic_search` / đọc `index.md`) → tổng hợp + cite.
- Câu trả lời hay → file ngược thành page mới (compounding).

### MCP bridge (cho AI khác)
- MCP = cầu nối: **chỉ đọc/tìm kiếm wiki** + **nạp context vào `raw/inbox/`** (`wiki_submit`).
- **KHÔNG** được viết thẳng vào `wiki/`. Edit wiki / ingest là việc maintainer.
- Đề xuất sửa → `wiki_propose_edit` (staging `wiki/.proposals/`), chờ người sign-off.

### Lint (định kỳ)
Tìm: contradiction (report người), stale claim, orphan page, missing xref, broken link, thiếu index entry, **frontmatter thiếu `domain`/`kind`**, **domain mới chưa có `index.md`**, **sources: chứa `raw/inbox/...` local path**, **body inline `[[raw/inbox/...]]`**.

## Search

- Scale nhỏ: `index.md` đủ.
- Lớn hơn: hybrid BM25 (FTS5) + vector (fastembed) qua `wiki_search`. Mỗi result có `domain`/`kind`.
- Semantic chunk-level: `rag/index.py` → `rag/.rag_index/`, query `rag/search.py` hoặc MCP `semantic_search`.

## Nguyên tắc an toàn
- **AI proposes, human decides.** Re-derivable writes (index, log) tự làm. Asserting/irreversible → `wiki_propose_edit` staging, chờ sign-off.
- Contradiction là report cho người, không materialize thành edge trên lời model.
- Provenance bắt buộc. Không claim không dẫn nguồn.
- **Copied state drift:** wiki page KHÔNG chứa value move-able (SHA, line count, mtime, count tuyệt đối). Values nằm trong frontmatter (mtime) hoặc đọc live từ tooling.
