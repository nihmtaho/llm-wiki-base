# Typed Relations + Claims + Language Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic typed-relations layer (frontmatter `relations:` + inline `[[path|rel:...]]` → SQLite `links` table), a `## Claims` convention with per-claim provenance, an opt-in `japanese` language pack (grammar-point/vocab kinds + relation vocabulary), and the ingest-skill synthesis step that updates existing pages instead of forking them.

**Architecture:** Approach A (spec §3): pages declare relations as prose-adjacent YAML; a pure-Python parser (`tools/graph.py`) extracts them deterministically — no LLM in the extraction path, same contract as chunking. `reindex` is the reconcile step. Language packs are per-wiki TOML opt-ins resolved from `templates/langpacks/<pack>/`; they influence parser validation only — DB schema is pack-agnostic. Wikis without a pack see zero behavior change.

**Tech Stack:** Python 3.13, sqlite3 (stdlib), PyYAML (already used for frontmatter), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-09-typed-relations-design.md`

## Global Constraints

- Extraction/sync path is **deterministic Python only** — no LLM calls in `graph.py`, `db.py`, `ingest.py`, `reindex.py`, `lint.py`.
- `links` table PK is `(src, rel, dst)`; `origin` ∈ `{'frontmatter', 'inline', 'wikilink'}` exactly.
- Default edge for plain `[[path]]`/`[[path|alias]]` is `rel: related`.
- Reserved alias prefix is exactly `rel:`.
- No-pack wiki ⇒ parser skips pack validation entirely (regression-tested).
- No changes to retrieval/RRF, translation, `pages` table, or `eval/golden.toml`.
- `SCHEMA_VERSION` in `reindex.py` bumps 3 → 4 (old wikis need `reindex --full` once).
- Commit messages: conventional (`feat(scope): ...`), no AI attribution trailers (git-commit skill).

## Review Focus

- **Inline `[[path|rel:x]]` vs existing alias `[[path|Text]]`**: a normal alias starting with anything but `rel:` must keep producing a `related` edge and never be misparsed as a typed relation. → pinned by `test_extract_inline_typed_and_plain_alias` in Task 1.
- **Stale edges after page edit**: editing a page that drops a relation must GC the old edge on incremental `ingest`, not only on `--full`. → pinned by `test_sync_links_gcs_removed_edges` in Task 2.
- **Dedup across origins**: same (src, rel, dst) declared in frontmatter AND inline must yield ONE row with `origin='frontmatter'` and frontmatter's `note` winning. → pinned by `test_dedup_frontmatter_wins` in Task 1.
- **CJK content**: pages with Japanese text (〜たら, kana) must parse — no regex choking on multibyte. → pinned by `test_extract_frontmatter_japanese_note` in Task 1.
- **`reindex --full` rebuild**: full rebuild must produce the same `links` contents as incremental ingest of the same files (idempotence). → pinned by `test_reindex_full_equals_incremental` in Task 3.

---

### Task 1: `graph.py` — pure link extraction

**Files:**
- Create: `src/llm_wiki_base/base_tools/graph.py`
- Test: `tests/test_graph.py`

**Interfaces:**
- Consumes: `db.parse_frontmatter(txt) -> dict` (existing, `db.py`), `_WIKILINK_RE`-equivalent regex (re-declared locally in `graph.py`).
- Produces (Task 2+ rely on these exact names):
  - `@dataclass Link`: `rel: str`, `dst: str`, `note: str | None`, `src_footnote: str | None`, `origin: str`
  - `extract_links(txt: str) -> list[Link]` — pure, no I/O. `dst` normalized to path form, may carry `#anchor`. Duplicate (rel, dst) deduped with frontmatter origin winning.
  - `RESERVED_REL_PREFIX = "rel:"`
  - `DEFAULT_REL = "related"`

- [ ] **Step 1: Write failing tests** in `tests/test_graph.py`

Use the `_load_base_tools(tmp_path, monkeypatch)` pattern from `tests/test_reserved_index.py` (syspath-prepend `src/llm_wiki_base/base_tools`, purge cached modules, `import graph`).

Test names + assertions:
- `test_extract_frontmatter_relations`: page with frontmatter `relations: [{rel: contrast-with, target: wiki/languages/grammar-point/ba.md, note: "…", source: s1}]` → one `Link(rel='contrast-with', dst='wiki/languages/grammar-point/ba.md', note='…', src_footnote='s1', origin='frontmatter')`.
- `test_extract_frontmatter_japanese_note`: same, `note` contains `〜たら` — assert round-trip equality (CJK-safe).
- `test_extract_inline_typed`: body `[[wiki/x.md|rel:contrast-with]]` → `Link(rel='contrast-with', dst='wiki/x.md', note=None, origin='inline')`; body `[[wiki/x.md|rel:example-of|Ví dụ]]` → `note='Ví dụ'`.
- `test_extract_plain_wikilink_default_rel`: `[[wiki/x.md]]` and `[[wiki/x.md|alias text]]` → `rel='related'`, `origin='wikilink'`, `note='alias text'` for the alias form.
- `test_dedup_frontmatter_wins`: same (rel, dst) in frontmatter (note='fm note') and inline (note='inline note') → exactly one Link, `origin='frontmatter'`, `note='fm note'`.
- `test_extract_claim_anchor`: body line inside `## Claims` section: `- claim text.[^s2] [[wiki/languages/grammar-point/ba.md#claims|rel:contradicts]]` → `Link(rel='contradicts', dst='wiki/languages/grammar-point/ba.md#claims', note='claim text.', origin='inline')`. (For links inside `## Claims` whose rel is `contradicts`, `note` = the claim bullet's text, stripped of footnote markers. Outside `## Claims`, inline note handling stays as in `test_extract_inline_typed`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_graph.py -v` (fallback `python3 -m pytest`)
Expected: FAIL — `ModuleNotFoundError: No module named 'graph'` (or ImportError).

- [ ] **Step 3: Implement `graph.py`**

- `Link` dataclass per Interfaces.
- `extract_links(txt)`:
  - Parse frontmatter via `db.parse_frontmatter`; read `relations` key (list of dicts with `rel`/`target`/`note`/`source`).
  - Regex-scan the body (lint's `_split_frontmatter` equivalent: strip the frontmatter block before scanning) for `[[...]]`; split inner on `|` → `(target, alias)`. Alias starting with `RESERVED_REL_PREFIX` → typed: `rel = alias[len(prefix):].split('|')[0]`, optional third pipe-segment = note. Otherwise → `rel=DEFAULT_REL`, note=alias.
  - `## Claims` section tracking: a simple line-state flag toggled by `^## Claims` heading until next `^## ` heading; within it, typed links with rel `contradicts` get `note` = owning bullet text (last non-empty line starting with `- `), footnote markers `[^id]` stripped.
  - Dedup key `(rel, dst)`, priority frontmatter > inline > wikilink.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_graph.py -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/base_tools/graph.py tests/test_graph.py
git commit -m "feat(graph): deterministic typed-relation link extraction"
```

---

### Task 2: `links` table + `sync_links` (db.py)

**Files:**
- Modify: `src/llm_wiki_base/base_tools/db.py` (add `links` DDL to `init_db` at line ~219 region; add sync functions after `delete_page`)
- Test: `tests/test_graph.py` (append)

**Interfaces:**
- Consumes: `graph.extract_links`, `graph.Link` (Task 1).
- Produces:
  - `db.init_db` additionally creates `links` (DDL verbatim from spec §4.1) — existing callers get it for free.
  - `sync_links(conn, path: str, txt: str) -> int` — extracts from `txt`, upserts edges with `src=path`, GCs rows `WHERE src=path` not in the fresh set, commits, returns edge count.
  - `get_links(conn, path: str) -> list[dict]` — rows for one src (test/lint helper).

- [ ] **Step 1: Write failing tests** (append to `tests/test_graph.py`, same loader)

- `test_sync_links_upserts`: in-memory DB, `sync_links(conn, 'wiki/a.md', page_with_frontmatter_relation)` → `get_links` returns 1 row, fields match, `src='wiki/a.md'`.
- `test_sync_links_gcs_removed_edges`: sync page with 2 edges → re-sync edited text with only 1 → `get_links` returns exactly the surviving edge.
- `test_links_table_in_init_db`: fresh `:memory:` conn, `init_db`, `SELECT name FROM sqlite_master WHERE name='links'` → present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_graph.py -v`
Expected: new tests FAIL (`sync_links` not defined / no `links` table).

- [ ] **Step 3: Implement**

In `init_db`, after the `chunks_fts` block, add the `links` DDL + `CREATE INDEX IF NOT EXISTS idx_links_dst ON links(dst)`.
Add `sync_links(conn, path, txt)` and `get_links(conn, path)` after `delete_page`. Upsert via `INSERT ... ON CONFLICT(src, rel, dst) DO UPDATE SET note=..., src_footnote=..., origin=...`; GC via `DELETE FROM links WHERE src=? AND rel NOT IN (...)`-style (build a temp set comparison in Python — simpler and CJK-safe).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_graph.py -v` — all PASS (including Task 1's).

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/base_tools/db.py tests/test_graph.py
git commit -m "feat(db): links table + deterministic sync_links"
```

---

### Task 3: Wire into `ingest.py` + `reindex.py` (SCHEMA_VERSION 4)

**Files:**
- Modify: `src/llm_wiki_base/base_tools/ingest.py` (after `search.index_file` call, line ~50)
- Modify: `src/llm_wiki_base/base_tools/reindex.py` (`SCHEMA_VERSION` at line 45; sync call in the per-file indexing loop)
- Test: `tests/test_graph.py` (append)

**Interfaces:**
- Consumes: `db.sync_links(conn, path, txt)` (Task 2).
- Produces: `ingest.py <path>` and `llm-wiki-base reindex` leave `links` in sync with page files. `SCHEMA_VERSION = 4`.

- [ ] **Step 1: Write failing test**

`test_ingest_cli_syncs_links`: temp wiki root with a real page file containing a frontmatter relation; run `ingest.py` via `subprocess` with `WIKI_ROOT` env set (mirror how existing CLI-scope tests invoke, or call `ingest.main` with `monkeypatch.setattr(sys, 'argv', ...)`); then open the same DB and assert the edge row exists. Keep vector off (config default in tmp root) so no embedding is needed.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_graph.py::test_ingest_cli_syncs_links -v` — FAIL (no row).

- [ ] **Step 3: Implement**

`ingest.py`: after `search.index_file(...)`, add `db.sync_links(c, rel, content)` (same `rel` normalized to forward slashes).
`reindex.py`: bump `SCHEMA_VERSION = 4` with comment `# 4: links table (typed relations) — wiki cũ cần reindex --full`; in the loop that indexes changed files, call `db.sync_links(conn, rel, content)`; for `--full`, delete all `links` rows first then rely on per-file sync.

- [ ] **Step 4: Run test + full suite**

Run: `.venv/bin/pytest tests/test_graph.py -v` then `.venv/bin/pytest tests/ -q` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/base_tools/ingest.py src/llm_wiki_base/base_tools/reindex.py tests/test_graph.py
git commit -m "feat(ingest): sync typed-relation links on ingest and reindex (schema v4)"
```

---

### Task 4: Language pack loading + japanese pack templates

**Files:**
- Create: `src/llm_wiki_base/templates/langpacks/japanese/kinds.yml`
- Create: `src/llm_wiki_base/templates/langpacks/japanese/relations.yml`
- Create: `src/llm_wiki_base/templates/langpacks/japanese/schema-notes.md`
- Modify: `src/llm_wiki_base/base_tools/graph.py` (pack-aware validation hook)
- Modify: `src/llm_wiki_base/templates/llm-wiki-base.toml` (commented `[langpack]` section)
- Test: `tests/test_graph.py` (append)

**Interfaces:**
- Consumes: `config_file.get_config(wiki_root)` (existing).
- Produces:
  - `load_langpack(wiki_root: str) -> dict | None` in `graph.py` — reads `[langpack]` from the wiki's toml via `get_config`; `enabled` falsy or `pack` empty → `None`; else loads `templates/langpacks/<pack>/{kinds.yml,relations.yml}` from the installed package (via `importlib.resources` or `os.path` relative to `graph.__file__`'s package root — follow how templates are resolved elsewhere in the codebase) → `{'kinds': {...}, 'relations': {...}, 'name': pack}`.
  - `validate_links(links: list[Link], pack: dict | None) -> list[str]` — returns error strings: unknown rel (not in `pack['relations']`, and `related` always allowed); `covered-in` (or any rel with `targets: [source]` constraint) whose dst kind path isn't a `source/` path. `pack=None` → `[]` always.
- File contents: `kinds.yml`/`relations.yml` verbatim from spec §6; `schema-notes.md` = the japanese-specific `_schema.md` additions (grammar-point/vocab field table, slug rule, `## Claims` Japanese example) — write from spec §5.3/§6.

- [ ] **Step 1: Write failing tests**

- `test_load_langpack_disabled_returns_none`: tmp wiki with toml lacking `[langpack]` → `None`.
- `test_load_langpack_japanese`: toml with `[langpack] enabled=true pack="japanese"` → dict with `grammar-point` in kinds and `contrast-with` + `covered-in` in relations.
- `test_validate_unknown_rel`: `validate_links([Link(rel='vague-rel', dst='wiki/x.md', ...)], pack)` → 1 error containing `unknown-rel-type`.
- `test_validate_targets_constraint`: rel `covered-in` with dst `wiki/languages/concept/x.md` → error; dst `wiki/languages/source/x.md` → no error.
- `test_validate_no_pack_passthrough`: `validate_links([...anything...], None)` → `[]`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_graph.py -k langpack -v` — FAIL (`load_langpack` not defined).

- [ ] **Step 3: Implement**

`load_langpack` + `validate_links` in `graph.py` (validation hook only — extraction stays pack-free). Template TOML gains a commented block:

```toml
# [langpack]
# enabled = true
# pack = "japanese"   # kinds grammar-point/vocab + relation vocabulary — xem docs/langpacks.md
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_graph.py -v` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/templates/langpacks/ src/llm_wiki_base/base_tools/graph.py src/llm_wiki_base/templates/llm-wiki-base.toml tests/test_graph.py
git commit -m "feat(langpack): opt-in japanese pack (kinds, relations, schema notes)"
```

---

### Task 5: Lint rules for relations + claims

**Files:**
- Modify: `src/llm_wiki_base/base_tools/lint.py` (new `_check_relations` function; call from `lint()` near `_check_wikilinks`, line ~166/250 region)
- Test: `tests/test_lint_relations.py`

**Interfaces:**
- Consumes: `graph.extract_links`, `graph.load_langpack`, `graph.validate_links` (Tasks 1, 4); `lint._split_frontmatter` (existing).
- Produces: findings added via `add(path, msg)` with exact prefixes: `broken-relation-target`, `unknown-rel-type`, `langpack-field-missing`, `claim-without-footnote`, `relation-without-note`, `inline-rel-vs-alias` (spec §8 severity table; advisory-only rules emit the same `add` channel — follow how existing lint distinguishes severity in its report structure).

- [ ] **Step 1: Write failing tests** in `tests/test_lint_relations.py`

Reuse the DB+tmp-wiki-root pattern from `tests/test_reserved_index.py`. Write a helper that creates a minimal page file and runs `lint.lint(conn, wiki_root=...)`, asserting on `result` findings.

- `test_broken_relation_target`: relation to `wiki/languages/grammar-point/missing.md` (file absent) → finding contains `broken-relation-target`.
- `test_unknown_rel_type`: rel `vague-rel` with japanese pack enabled in tmp toml → `unknown-rel-type`.
- `test_claim_without_footnote`: `## Claims` bullet without `[^id]` → `claim-without-footnote`.
- `test_relation_without_note_contrast`: `contrast-with` without `note` → advisory finding `relation-without-note`.
- `test_inline_rel_vs_alias`: same dst, inline `rel:contrast-with` AND alias `[[dst|contrast-with]]`-style conflict → `inline-rel-vs-alias`.
- `test_no_pack_no_unknown_rel`: same `vague-rel`, NO pack → no `unknown-rel-type` (regression: pack-free wiki unchanged).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_lint_relations.py -v` — FAIL.

- [ ] **Step 3: Implement `_check_relations(path, txt, WIKI_ROOT, add, pack)`**

- Extract links, check each dst file exists (strip `#anchor`) → `broken-relation-target` (CRITICAL).
- `validate_links(links, pack)` errors → `unknown-rel-type` findings.
- Scan `## Claims` bullets: `- ...` lines without `[^` → `claim-without-footnote`.
- `contrast-with`/`contradicts` links with empty `note` → `relation-without-note` (advisory).
- Inline typed vs plain-alias conflict on same dst → `inline-rel-vs-alias` (advisory).
- `langpack-field-missing`: if pack on, for each page whose path starts with a kind's `path` prefix, required fields absent from frontmatter → CRITICAL finding. (Reuse `db.parse_frontmatter`.)

- [ ] **Step 4: Run tests + full suite**

Run: `.venv/bin/pytest tests/test_lint_relations.py -v` then `.venv/bin/pytest tests/ -q` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/base_tools/lint.py tests/test_lint_relations.py
git commit -m "feat(lint): relation/claim rules (broken target, unknown rel, claims provenance)"
```

---

### Task 6: Skill + schema template updates (synthesis step, contract)

**Files:**
- Modify: `src/llm_wiki_base/skills/wiki/llm-wiki-base-ingest/SKILL.md` (insert §2.5 SYNTHESIS PASS between Workflow steps 2 and 3; reword profile page-count note to exclude synthesis-in-place)
- Modify: `src/llm_wiki_base/templates/agents/_schema.md` (relations frontmatter, inline syntax, `## Claims` convention — from spec §5)
- Test: `tests/test_global_skills.py` or a new `tests/test_schema_template.py` asserting the skill file contains the `SYNTHESIS PASS` heading and `_schema.md` contains `relations:` + `## Claims` (template-content regression guards, cheap).

**Interfaces:**
- Consumes: spec §5, §7 verbatim copy.
- Produces: deployed wikis (post `init`/upgrade) carry the new contract; skill workflow includes synthesis.

- [ ] **Step 1: Write failing test**

`test_ingest_skill_has_synthesis_pass` and `test_schema_template_documents_relations_and_claims` reading the two template paths from the package.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_schema_template.py -v` — FAIL.

- [ ] **Step 3: Edit the two templates**

SKILL.md §2.5 = spec §7 copy. `_schema.md`: new "Relations & Claims" section = spec §5 (frontmatter block, inline syntax with reserved `rel:` prefix, `## Claims` rules, contradiction→alert policy), plus a pointer to `docs/relations.md`.

- [ ] **Step 4: Run tests + full suite**

Run: `.venv/bin/pytest tests/test_schema_template.py -v`, `.venv/bin/pytest tests/ -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/skills/wiki/llm-wiki-base-ingest/SKILL.md src/llm_wiki_base/templates/agents/_schema.md tests/test_schema_template.py
git commit -m "feat(ingest-skill): synthesis pass + schema contract for relations/claims"
```

---

### Task 7: User documentation + migration guide + AGENTS.md

**Files:**
- Create: `docs/relations.md` (user guide — spec §10 content: syntax, worked Japanese before/after example, claims, contradictions policy, enabling langpack, "old pages stay valid; add relations as consolidate touches them")
- Create: `docs/langpacks.md` (creating a pack; `kinds.yml`/`relations.yml` reference; japanese pack as canonical example)
- Create: `docs/migration-relations.md` (per-wiki upgrade: re-run `llm-wiki-base init` → sync skills/schema; `llm-wiki-base reindex --full` → build `links`; no content changes required)
- Modify: `AGENTS.md` (Operations → Ingest: insert synthesis step reference; Tooling line: add `tools/graph.py`)

**Interfaces:**
- Consumes: everything above; spec §10.
- Produces: shipped docs.

- [ ] **Step 1: Write the three docs + AGENTS.md edits** (from spec §§5–8, 10; worked example uses Shinkanzen/Minna `〜たら` vs `〜ば` from the japanese wiki)

- [ ] **Step 2: Verify links + consistency**

Run: `llm-wiki-base lint` in the repo's own wiki if wired; else manually confirm every doc cross-reference resolves and command names match `--help` output (`llm-wiki-base reindex --full`, `llm-wiki-base init`).

- [ ] **Step 3: Commit**

```bash
git add docs/relations.md docs/langpacks.md docs/migration-relations.md AGENTS.md
git commit -m "docs: relations/langpack user guides, migration guide, runbook update"
```

---

### Task 8: End-to-end smoke + whole-branch review

- [ ] **Step 1: Full test suite + CLI smoke**

Run: `.venv/bin/pytest tests/ -q` — all PASS.
Create a throwaway wiki dir with a japanese-pack toml, two pages with relations + claims, run `llm-wiki-base reindex` then `llm-wiki-base lint` — confirm `links` rows via sqlite3 CLI and expected findings. Throwaway artifacts deleted afterward (spike hygiene).

- [ ] **Step 2: Whole-branch review** via superpowers:requesting-code-review against spec §1–§12 coverage.

- [ ] **Step 3: Merge decision** via superpowers:finishing-a-development-branch.
