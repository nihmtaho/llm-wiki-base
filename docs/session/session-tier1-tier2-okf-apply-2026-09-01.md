# Session — Áp dụng Tier 1 + Tier 2 từ idea bundle vào llm-wiki-base

- **Ngày**: 2026-09-01
- **Nguồn**: đánh giá `docs/human-ideas/my-idea/` (OKF v0.2 bundle + 6 skill-idea + wiki.config.toml)
- **Plan**: `~/.commandcode/plans/llm-wiki-tier1-tier2-implementation.md`
- **Trạng thái**: hoàn tất implementation + verification. **Chưa commit.**

---

## 1. Đánh giá idea bundle

Đọc toàn bộ idea bundle và đối chiếu với code hiện tại (lint.py, db.py, search.py, rag/index.py, skills, _schema.md). Phân loại thành 3 tier:

- **Tier 1** (apply ngay): TOML config per-wiki, lint deterministic mở rộng, incremental reindex, chunking fixes, trust fields, relax_recall.
- **Tier 2** (cần sửa skill/schema): footnote per-claim citation, tách lint/review + alerts, consolidate skill, pins.yml, query theo trust tier.
- **Tier 3** (defer): OKF full conformance, union retrieval + RRF + rerank, chunk-level BM25, eval harness, codebase profile g3doc, Attested Computation, registry.yml, private dirs, wikilink export.

Phát hiện thực tế từ code trong lúc đánh giá:
- lint.py **không check broken-wikilink target** (chỉ dùng link để tính orphan).
- `_chunk_markdown(text, max_chars=1200)` **bỏ qua max_chars** — chunks không bị cắt; index cả frontmatter + footnote.
- `config_file._write_toml` cast int → string, không support nested table.
- search.py đọc `WIKI_BM25_WEIGHT`/`VEC_WEIGHT` ở **module level** — sai với MCP multi-wiki (`_set_wiki_ctx` đổi WIKI_ROOT per-call).

## 2. Quyết định config TOML

- `.llm-wiki.toml` để **per-wiki** (wiki root) — mọi section đều là hành vi của wiki cụ thể; commit vào wiki repo; `.env` gitignored (runtime plumbing).
- Global `~/.llm-wiki-base/` chỉ giữ `registry.toml` (MCP routing) — không đổi.
- Áp cho **cả personal + project** profile.
- **Verify workflow dùng chung cả personal + project** (chỉnh từ feedback: ban đầu plan chỉ nhấn personal).

## 3. Implementation (7 phase)

### Phase 1 — Config foundation
- `pyproject.toml` + `src/llm_wiki/requirements.txt`: thêm `tomli-w>=1`.
- `src/llm_wiki/config_file.py`: writer chuyển sang `tomli_w` (sửa bug int→string, support nested); thêm `DEFAULTS` + `get_config()` (deep-merge) + `effective()` (env > TOML > builtin).
- `src/llm_wiki/base_tools/config_file.py`: **mới** — shim read-only theo pattern `paths.py` (global venv không có package).
- `src/llm_wiki/templates/llm-wiki.toml`: **mới** — template đầy đủ sections, comment tiếng Việt.
- `init_personal.py` / `init_project.py`: copy template vào wiki (guard exists); dọn `.env` template.
- `cli.py`: group `config show` in effective config kèm nguồn (default/toml/env).

### Phase 2 — Reindex incremental + chunking + search
- `base_tools/db.py`: cột `content_hash TEXT` (ALTER migration pattern sẵn có); `upsert_page` nhận hash.
- `base_tools/reindex.py`: viết lại — incremental theo content-hash, `--full`, `--check` (dry-run), meta drift `.index_meta.json`, warning khi config đổi.
- `base_rag/index.py`: viết lại — `build_index(full, check)`, splice vectors theo file-hash, rebuild khi đổi `embed_model`/`chunk_tokens`; `vector=false` → skip; chunking honor `max_chars` (= `chunk_tokens × 4`), loại frontmatter + footnote khỏi chunk.
- `base_rag/search.py` + `embeddings.py`: sửa path resolution hoạt động cả src-layout lẫn deployed layout; query provider đọc model từ config; guard empty index.
- `base_tools/search.py`: weights + `relax_recall` + flag `vector` đọc **per-call** từ config; `_fts_or_query` sanitize term (fix term có `-` làm FTS5 error).
- `base_tools/watch.py`: `rebuild_rag` incremental; `WATCH_RAG_SEC` default 1800→600; log `[review] due` khi quá cadence.
- `base_tools/ingest.py`: embed theo config (vector off → BM25-only).
- `cli.py`: `reindex --full/--check`.

### Phase 3 — Lint deterministic mở rộng
`base_tools/lint.py` viết lại — giữ nguyên API dict (MCP `wiki_lint` không đổi). Checks mới: `broken-wikilink`, `missing-frontmatter`, `missing-index-entry`, `domain-missing-index` (dedupe), `timestamp-format`, `status-vocab` (thêm planned/deprecated/superseded), `footnote-sources-match`, `stale-after-passed`, `pin-orphan`, `banned-terms`/`dense-bullet`/`indent-depth` (từ `[lint]` config). `--fix` thêm `fix_index_entries()` (additive) + tạo index.md cho domain thiếu.

### Phase 4 — Schema
- `base_tools/db.py`: `parse_frontmatter` support inline dict (`generated: {by, at}`) + block list-of-dicts trong `sources:` — dual-format backward compat.
- `templates/agents/_schema.md`: trust tier (unverified → machine-confirmed → human-reviewed), sources dict form + footnote `[^id]` trích verbatim + distill-verify rule, `status: planned` (chống fork, không cần registry.yml), `kind: alert`, pins.yml, alerts, `llm-wiki verify`.

### Phase 5 — Skills + verify CLI
- Skill mới: `llm-wiki-review`, `llm-wiki-consolidate` (personal) + `wiki-project-review`, `wiki-project-consolidate` (project) — alerts queue `wiki/alerts/`, auto-close 2-lần-vắng, cadence gate + watermark `.review_state.json`, consolidate có distill-verify (citation không co).
- Cập nhật: `llm-wiki-ingest`, `llm-wiki-query`, `llm-wiki-lint`, `wiki-project-ingest`, `wiki-project-lint`, `wiki-project-research` — sources dict + footnote, `generated` (không set `verified`), check `planned` trước create, tôn trọng pins, trust tier flags khi query, reindex incremental, tách semantic sang review.
- `src/llm_wiki/verify.py`: **mới** — set/clear `verified: {by: "human:<id>", at}` deterministic.
- `cli.py`: lệnh `verify` (+`--unverify`, `--root`). **Bug đã fix**: import hàm `unverify` shadow tham số bool `unverify` → luôn True; đổi sang import module.

### Phase 6 — Templates + docs
- `templates/agents/AGENTS.md` + `CLAUDE.md`: sections Review/Consolidate/alerts/pins/verify, TOML config thay env hints, log op vocab thêm `review|consolidate|verify`, reindex incremental.
- `templates/wiki-gitignore`: thêm `wiki/.review_state.json`, `.consolidate_state.json`, `.index_meta.json`.
- `README.md`: skills table (6 personal + 7 project), CLI operations mới, section **Config (.llm-wiki.toml)** + **Verify & trust tier**.

### Phase 7 — Tier 3 roadmap
- `docs/tier3-roadmap.md`: **mới** — 10 mục deferred: eval harness (P@k/R@k/MRR → điều kiện bật vector), union retrieval + RRF + rerank, chunk-level BM25, OKF v0.2 full conformance, codebase profile g3doc, registry.yml multi-agent, Attested Computation, `[private] dirs`, lint-export wikilink rewrite, migration tooling.

## 4. Verification (tất cả pass)

1. Compile toàn bộ `.py` — OK.
2. `pip install -e .` + `llm-wiki base install` — sync global base OK.
3. Fresh `init personal` (scratch, `--no-mcp`): `.llm-wiki.toml` được tạo, **6 skills** (gồm review + consolidate mới) — OK.
4. `config show` in đúng effective config kèm nguồn — OK.
5. Lint: từng check mới bắn đúng (broken-wikilink, status-vocab, timestamp, stale-after-passed, dense-bullet, domain-missing-index dedupe, pin-orphan, footnote-sources-match) — OK.
6. `lint --fix` tạo index.md + thêm entries — OK.
7. Reindex: `--check` dry-run 0 file; sửa 1 page → chỉ re-index đúng 1; `--full` rebuild; `vector=false` → "vector skipped" nhưng BM25 vẫn chạy — OK.
8. RAG vector: full rebuild + incremental splice + `semantic_search` trả kết quả — OK.
9. `relax_recall`: AND-match 0 → OR retry trả kết quả (kể cả term có `-`) — OK.
10. `verify` set → `verified: {by: "human:nihmtaho", at: ...}`; `--unverify` xoá sạch; `parse_frontmatter` parse dict — OK.
11. Project init: `.llm-wiki.toml` + `wiki-project-review`/`wiki-project-consolidate` — OK.
12. MCP `mcp_base_server` import + `lint.lint()` qua dict findings mới — OK.
13. Backward compat: wiki cũ flat sources + page mới dict sources共存, reindex + lint không lỗi — OK.

## 5. Files changed

**Modified (27)**: `pyproject.toml`, `src/llm_wiki/requirements.txt`, `config_file.py`, `cli.py`, `verify.py`*(new)*, `init_personal.py`, `init_project.py`, `base_tools/{config_file*(new)*, db, search, reindex, watch, ingest, lint}.py`, `base_rag/{index, search, embeddings}.py`, `templates/{llm-wiki.toml*(new)*, wiki-gitignore}`, `templates/agents/{_schema, AGENTS, CLAUDE}.md`, `skills/personal/{llm-wiki-ingest, llm-wiki-query, llm-wiki-lint}/SKILL.md`, `skills/project/{wiki-project-ingest, wiki-project-lint, wiki-project-research}/SKILL.md`, `README.md`, `docs/tier3-roadmap.md`*(new)*.

**New (8)**: `src/llm_wiki/verify.py`, `src/llm_wiki/base_tools/config_file.py`, `src/llm_wiki/templates/llm-wiki.toml`, `src/llm_wiki/skills/personal/llm-wiki-review/SKILL.md`, `src/llm_wiki/skills/personal/llm-wiki-consolidate/SKILL.md`, `src/llm_wiki/skills/project/wiki-project-review/SKILL.md`, `src/llm_wiki/skills/project/wiki-project-consolidate/SKILL.md`, `docs/tier3-roadmap.md`.

## 6. Ghi chú

- **Chưa commit** — change set nằm ở working tree.
- Sau pull trên máy khác: chạy `pip install -e .` rồi `llm-wiki base install` để sync tools vào global base.
- Không migrate wiki cũ tự động — mọi field mới đều optional; lint báo advisory; wiki cũ flat-sources vẫn parse được.
- Lần chạy test đầu không set `WIKI_ROOT` env → lỗi `unable to open database file` (CLI wrapper thường set; test trực tiếp phải export).
