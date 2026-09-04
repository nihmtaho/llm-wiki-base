# LLM Wiki — Schema

Data contracts for the wiki. Workflows live in the runbook (`AGENTS.md`; `.claude/CLAUDE.md` only tags `@AGENTS.md`).

The wiki is a cumulatively-built artifact maintained by an LLM. Compile once, keep current.

## Data flow

- `raw/inbox/` — staging. New files awaiting ingest. Mutable while humans/AIs drop files in.
- `raw/` — **local cache** post-ingest (URL and non-URL alike). **Deletable at will** — provenance lives in the page's `sources:` field. Gitignored by default.
- `wiki/` — markdown generated/maintained by the LLM. The LLM owns this layer. **This is the real knowledge** (curated, cross-linked, persistent).

Move rules:
- Sources with OR without a URL → all move from `raw/inbox/` to `raw/`. Provenance differs only in the `sources:` field (URL = strong, `[]` = weak).
- `raw/inbox/` is staging only — files here are not yet ingested.
- `raw/` (outside inbox) is local cache. Users may delete at will; to pin manually: `git add -f raw/<file>`.
- Body text never links `[[raw/inbox/...]]` inline — only the `sources:` field may (see rule 4 below). `[[raw/...]]` (outside inbox) is allowed since the user manages it.

## Domains (top-level folders under `wiki/`)

**Domain = the top-level folder directly under `wiki/`** — count is **unbounded**. Folder names are auto-detected by the agent from raw content + title + URL.

**Naming rule for new domains** (used by the agent when auto-creating):
- One clear framework/library → its kebab-case name (`expo-ecosystem`, `react-navigation`, `claude-code`).
- One course / series → the series kebab-case name (`minna-no-nihongo`).
- One internal project → the project kebab-case name (`my-project`).
- Broad area with no clear project → create with a descriptive name (e.g. `distributed-systems`).
- Lowercase, kebab-case, ASCII-safe.

## Structure inside each domain

Each domain folder has its own `index.md` + pages by **kind** (semantic role):
- `entity/` — entities (frameworks, people, orgs, libraries, tools).
- `concept/` — concepts / patterns / theory.
- `source/` — raw-source summaries.
- `task/` — only in domains with task tracking.
- Contextual subfolders: `vocab/` (languages), `analysis/`, `comparison/`...

## Page conventions

Frontmatter YAML:
```yaml
title: ...
domain: <top-level folder name>
kind: source|concept|entity|task|alert
tags: [...]
sources: ...                      # provenance — 2 forms, see rule below
updated: YYYY-MM-DD
status: draft|active|done|stale|planned|deprecated|superseded
confidence: unverified|human-verified|machine-confirmed|superseded   # legacy
# --- trust fields (optional, recommended for new pages) ---
generated: {by: "<tool>/<model>", at: 2026-09-01T09:00:00+07:00}
verified:  {by: "human:<id>",     at: 2026-09-01T10:00:00+07:00}  # absent = unverified
stale_after: 2027-01-01T00:00:00+07:00   # past due → lint reports stale-after-passed
x_owner: "human:<id>"
x_supersedes: wiki/<domain>/concept/<old>   # when status: superseded
```

**`sources:` field rule:**

`sources:` accepts **2 forms** (dual-format — flat lists stay valid for old pages):

- **Flat list (legacy)**: `sources: [<url>...] | [<wiki-xref>...] | []`
- **List-of-dicts (recommended for new pages)** — per-claim citation via footnote:
```yaml
sources:
  - id: s1
    resource: https://example.com/api/     # URL, wiki-xref, or raw/ path
    title: "API docs"
```
  Cite each claim in body: `Important claim.[^s1]` + closing footnote with verbatim quote:
  ```
  [^s1]: API docs
      > [human:<id>] "prod must be Postgres, SQLite is for local testing only"
  ```
  Lint check `footnote-sources-match`: every `[^id]` must match a `sources[].id` and vice versa.
  **Distill-verify**: when merging/consolidating, the page's citation set must NOT shrink.

General rules (both forms):
1. **Original URL** when the raw file has `source: <url>` (docs/blog/GitHub) — strongest provenance. Multiple URLs OK.
2. **Wiki cross-link** `[[wiki/<domain>/source/<other>]]` when the claim builds on another source page in the wiki.
3. **`sources: []`** when the page has no original URL (task intake, internal logs, personal writing) OR when the `raw/` file is intermediate (already moved out of `raw/inbox/`).
4. **NEVER** record `raw/inbox/...` in `sources:` — it's staging, violating the copied-state rule (local paths may rename/move while the wiki page still points at the old path). `raw/` (outside inbox) is citable since the user controls its commit/backup.
5. **NEVER** link to `raw/inbox/` in body text — only in the `sources:` field. `[[raw/...]]` (outside inbox) allowed — the user's call.

Valid examples:
```yaml
sources: [https://docs.example.com/api/]
sources: [https://docs.example.com/api/, https://github.com/foo/bar]
sources: [wiki/<domain>/source/<other>.md]
sources: [https://docs.example.com/api/, wiki/<domain>/source/<other>.md]
sources: []
```

- Every important claim carries provenance: a `[[wiki page]]` link in body or a URL in `sources:`.
- Task pages add: `status` (todo|doing|done|blocked), `priority`, `assignee`, `due`, `depends_on`.
- Kanban = `wiki/projects/kanban.md`, 3 columns (Todo / Doing / Done), one task-page link per line.

**Backwards-compat:** old pages with only `category: <folder>` (no `domain`/`kind`) → inferred automatically from path.

## Wikilinks

- **Full path only**: `[[wiki/<domain>/<kind>/<slug>]]`.
- **No markdown wrapping**: `[text]([[path]])` breaks Obsidian rendering.
- Custom text → alias: `[[path|Custom Text]]`.
- Never link `[[raw/inbox/...]]` in body (staging); `[[raw/...]]` outside inbox is allowed.

## Trust tier & verify (personal + project)

- **unverified** — no `verified` (default for AI-written; `generated` records who/when).
- **machine-confirmed** — `verified.by` is an agent (deterministic machine check).
- **human-reviewed** — `verified.by` = `human:<id>`. Only this tier is canonical for JUDGMENT.

**Reviewing an artifact = setting `verified`** (shared by personal + project wikis):

```bash
llm-wiki verify wiki/<domain>/concept/<slug>.md --by <human-id>   # set verified → human-reviewed
llm-wiki verify <path> --unverify                                 # drop verified (back to unverified)
```

AI NEVER sets `verified` itself. Consolidate/review touching judgment content → `--unverify` that part, await human re-review.

## Anti-fork — status: planned

Before creating a page, look up a `status: planned` page with the same slug in the DB: found → **update**, don't create.
Reserve = create a `status: planned` placeholder before generating content; later ingest sees planned → fills in + `status: active`. No separate registry file needed.

## Pins — wiki/pins.yml (human hand-edits, survive regeneration)

```yaml
- concept: wiki/<domain>/concept/<slug>
  kind: correction            # correction | addition | deletion
  claim: "Content the human wants to keep"
  anchor: "## <heading>"      # section the pin anchors to
  provenance: "human:<id>"
  status: active
```

- Ingest/consolidate do NOT overwrite sections an `active` pin anchors to.
- New sources contradicting a pin → push to `wiki/alerts/`, NEVER revert silently.
- Lint check `pin-orphan`: anchor heading gone / concept missing → report to human (never delete pins).

## Alerts — wiki/alerts/ (gap queue)

- Review-skill gaps (contradiction, stale, trust gap, pin conflict) become pages with
  frontmatter `domain: alerts, kind: alert, status: open, last_seen: <date>`.
- A gap not re-raised across two consecutive review runs → `status: closed` (auto-close).
- Pseudo-domain: still has `wiki/alerts/index.md`, still indexed/searched.

## Search

Markdown is the source of truth; all indexes (DB FTS, `rag/.rag_index/`) are **derived**,
throwable, rebuildable — NEVER commit.

- Small scale: `index.md` suffices.
- **Union retrieval** (MCP `wiki_search` / `tools/search.py:hybrid_search`) — 3 independently
  ranked channels fused by **RRF over rank** (never summed scores: `bm25()` and cosine
  live on different scales):
  | channel | infra | off when |
  |---|---|---|
  | `bm25_page` | FTS5 `pages_fts` (wiki + raw) | FTS5 missing |
  | `bm25_chunk` | FTS5 `chunks_fts` in `.wiki.db` | `chunk_bm25=false` or no `reindex --full` yet |
  | `vector_chunk` | `rag/.rag_index/{chunks.json,vectors.npy}` | `vector=false`, not built, model missing |
- Results carry `matched_by` (which channels hit) + `rank` + `snippet` (possibly
  **one chunk's text**) → enough to PICK a page, not to answer.
- **Chunks only find concepts.** Answers quote compiled concepts, citing the
  Concept path + `sources[].id` — trust tier preserved, never quote raw chunks.
- Chunk = semantic section (by heading, heading kept as context), excluding
  frontmatter + verbatim footnotes. Reserved `index.md`/`log.md` and
  `*.lang.md` translations are **never** chunked.
- **Deterministic fallback**: missing model/embeddings/chunks → structural + BM25.
  "No model" ≠ "broken". Eval prints `[ERROR] channel disabled by error` when a channel
  dies of a real error (vs "disabled by config").
- Threshold: below ~100k tokens BM25 suffices. `vector = true` **only when**
  `llm-wiki eval --compare` shows recall/MRR gains.
- Config: `[retrieval]` in `.llm-wiki.toml` (`mode`, `fusion`, `rrf_k`,
  `chunk_bm25`, `vector`, `chunk_tokens`, `top_k_bm25`, `top_k_vector`,
  `top_n_final`, `relax_recall`, `[retrieval.weights]`). `rerank` is a **skill-layer**
  contract (Python never reads it).
