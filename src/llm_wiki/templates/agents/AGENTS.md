# LLM Wiki — Runbook

You are the **wiki maintainer**. The human supplies sources, questions, and reviews. You do everything else: read, summarize, cross-reference, lint, bookkeeping. The wiki compounds — compile once, maintain forever.

## Layout

- `raw/inbox/` — staging. New files awaiting ingest (mutable).
- `raw/` — **local cache** post-ingest (URL and non-URL alike). **Deletable at will** — provenance lives in the page's `sources:` field. Gitignored by default.
- `wiki/` — markdown you own. **This is the knowledge**: persistent, cross-linked.
- `wiki/.proposals/` — staging for human-gated edits (via MCP `wiki_propose_edit`).
- `wiki/alerts/` — review gap queue (contradiction, stale, trust gap, pin conflict). Pseudo-domain; frontmatter `domain: alerts, kind: alert, status: open|closed`.
- `wiki/pins.yml` — human hand-edits (claim + anchor) that survive regeneration. Ingest/consolidate MUST NOT overwrite a section an `active` pin anchors.
- `wiki/index.md` / `wiki/log.md` — **reserved**: navigation + history. Still searchable pages, but **never chunked**.
- `eval/golden.toml` — golden retrieval queries (`llm-wiki eval`). **Data, COMMIT**. `eval/results.json` — measurement history, gitignored.
- `AGENTS.md` (this file) — conventions + workflows. Field details: `_schema.md`.

**Provenance:** curated pages outrank `raw/` (re-read cache); original URLs in `sources:` are primary truth. Full semantics: `_schema.md`.

## Domains

Top-level folders under `wiki/`, **unbounded**, auto-detected from raw content (kebab-case, lowercase, ASCII). Each has `index.md` + `entity/`/`concept/`/`source/`/`task/` pages. Full taxonomy + naming rule: `_schema.md`.

## Page conventions (full contract: `_schema.md`)

- Frontmatter: `title`, `domain`, `kind`, `tags`, `sources`, `updated`, `status` (+ legacy `confidence`); trust `generated`/`verified` (absent = unverified) + optional `stale_after`, `x_owner`, `x_supersedes`. **Never set `verified` yourself** (`llm-wiki verify … --by <id>`).
- `sources:` flat list (legacy) or `{id, resource, title}` dicts + per-claim `[^id]` footnotes; every material claim needs provenance.
- **Wikilinks, full path only**: `[[wiki/<domain>/<kind>/<slug>]]` (alias: `[[path|Custom Text]]`).
- **Anti-fork**: a `status: planned` page on the topic exists → update, don't create.
- Task fields + `wiki/projects/kanban.md`; legacy `category:`-only pages → infer from path.

## Runtime

- **Global runtime** `~/.llm-wiki-base/` (`tools/`, `rag/`, `scripts/`, `.venv/`, `requirements.txt`; override via `LLM_WIKI_BASE_DIR`). Shared by all wikis.
- **Per-wiki data** (`raw/`, `wiki/`, `rag/.rag_index/`, `.env`, `.llm-wiki.toml`). No code, no venv.
- Run the `llm-wiki <ingest|reindex|lint|watch>` wrappers (they call the global base). Never assume `tools/` lives inside the wiki.

## Skills

Installed by `llm-wiki init` into `.agents/skills/` (canonical; symlinked for Claude/OpenCode). Mode comes from `[wiki].profile` in `.llm-wiki.toml` — skill names don't vary by profile.

| skill | scope | job |
|---|---|---|
| `llm-wiki-ingest` | wiki | raw → source/entity/concept pages + index/log + reindex |
| `llm-wiki-query` | wiki | answer from **this** wiki (retrieval → rerank → cite) |
| `llm-wiki-lint` | wiki | deterministic health-check + `--fix` for re-derivable content |
| `llm-wiki-reindex` | wiki | build/diagnose derived indexes (`--check`/`--full`) |
| `llm-wiki-review` | wiki | semantic gaps: contradiction, stale, trust gap → `wiki/alerts/` |
| `llm-wiki-consolidate` | wiki | merge scraps → canonical concepts (additive) |
| `llm-wiki-translate` | wiki | translate pages into `[translate].langs` |
| `llm-wiki-research` | **codebase root** | cross-wiki research via centralized MCP |

`llm-wiki-research` lives at the repo root (it must see all wikis). Only the skill layer needs an LLM; CLI/Python is deterministic.

## Operations

### Ingest
1. Source arrives in `raw/inbox/` (human drop, `extract_*.py`, or MCP `wiki_submit` from another AI).
2. Read it, **auto-detect domain**, create `wiki/<domain>/` if new.
3. Write summary → `wiki/<domain>/source/<slug>.md` (`domain`, `kind: source`, `sources`, `updated`, `status: active`, `generated`). No URL → `sources: []` (never a local path — it drifts). **Never set `verified`.** Prefer list-of-dicts + `[^id]` citations.
4. Create/update related entity/concept pages in the same domain; every new page needs ≥1 outbound wikilink. Respect `active` pins; pin conflicts → `wiki/alerts/`, never a silent revert.
5. Translation enabled (`[translate]` in `.llm-wiki.toml`) → invoke `llm-wiki-translate` per new page (never translate inline).
6. Update `wiki/<domain>/index.md` (new domain → also add a row to `wiki/index.md`). Page count = `find wiki/<domain> -name "*.md" | wc -l` — count, don't guess.
7. Prepend to `wiki/log.md`: `## [YYYY-MM-DD HH:MM:SS] ingest | <title>` + bullets for actions actually taken. Date = the source page's `updated`.
8. `llm-wiki ingest <path> && llm-wiki reindex` (CLI only, never via MCP). `*.lang.md` + `index.md`/`log.md` skip chunking automatically.
9. Move the source `raw/inbox/<name>` → `raw/`.

### Query
`index.md` → `wiki_search` (pool `2 × top_n_final`) → **LLM rerank** on title/snippet/`matched_by` without opening files → open `top_n_final` pages → answer with cites. Good answers get filed back as new pages. Suspect retrieval → `llm-wiki eval --compare`. Detail: `llm-wiki-query` skill.

### Lint (deterministic) / Review (semantic) / Consolidate
- `llm-wiki lint`: orphan, broken wikilink, missing file (CRITICAL), frontmatter, status vocab, timestamps, footnote↔sources match, stale-after, missing index entries (`--fix` adds them), pin-orphan, `raw/inbox` leaking into `sources:`/body, style advisories.
- `llm-wiki-review` skill (past `[review].interval_days`): contradictions (report, never auto-resolve), stale claims/code refs, missing concepts, trust gaps, pin conflicts → `wiki/alerts/` (`status: open`; auto-close if not re-raised).
- `llm-wiki-consolidate` skill: merge scraps into canonical concepts, additive; duplicates → `superseded` + `x_supersedes`; judgment changes → `--unverify`.

### Translation (optional)
Parallel `<slug>.<lang>.md` files, same frontmatter, exact translation (code/URLs/terms preserved), **excluded from DB/RAG**. Config in `.llm-wiki.toml` (`[translate]` enabled + langs); `llm-wiki translate enable|status|disable|check`. Warn if `langs` > 5 or many pages (token cost).

## Safety
- **AI proposes, human decides.** Direct writes only for re-derivable content (index, log). Fact assertions → `wiki_propose_edit` staging.
- Contradictions are human reports, never new edges.
- No claim without provenance.
- **No copied moving state** in pages (SHAs, counts, mtimes) — frontmatter or live tooling only. Cite values only as history.

## Retrieval (full channel contract: `_schema.md`)

- Small scale: `index.md` suffices.
- **Union + RRF over rank** across `bm25_page`, `bm25_chunk`, `vector_chunk`. Results carry `matched_by` + `rank` + `snippet` (enough to *pick* a page, not to answer).
- **Rerank is the skill's job** (`rerank = "llm"`): wide pool, score on metadata, open `top_n_final`. No reranker model in code.
- Never chunked: `index.md`/`log.md`, `*.lang.md`, frontmatter, verbatim footnotes.
- Channels fail closed and loudly (`reindex --check`, eval `[ERROR]`); `fusion = "weighted"` is the one-line rollback / A-B baseline.
- Enable `vector = true` only on `eval --compare` evidence (R@k/MRR gain). Goldens in `eval/golden.toml` (commit).
- Behavior lives in `.llm-wiki.toml`; `WIKI_*` env vars override; `llm-wiki config show` reveals each value's source. Changing `embed_model`/`chunk_tokens`/`vector`/`fusion` → `reindex --full`.

## MCP bridge
Read/search (`wiki_search`, `semantic_search`, `wiki_read`, `wiki_list`, `list_raw_source`, `read_raw_source`) · intake `wiki_submit` → `raw/inbox/` · proposals `wiki_propose_edit` → `.proposals/`. Write tools REQUIRE `wiki=`. **MCP never ingests** — page writing is maintainer-only (CLI / `llm-wiki-ingest` skill).

## Tooling
`scripts/extract_{url,pdf,youtube}.py` → `raw/inbox/` · `tools/{paths,chunking,search,watch,ingest,reindex,eval}.py` · `rag/index.py` (vector chunks). Chunking is shared between BM25-chunk and vector-chunk — boundaries must match for RRF to mean anything.
