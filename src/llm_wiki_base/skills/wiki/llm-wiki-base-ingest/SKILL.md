---
name: llm-wiki-base-ingest
description: >
  Feed one raw source into the wiki and integrate it as concepts — auto-detect domain, read,
  summarize, cross-link entity/concept, update index/log, incremental reindex. Use when a new
  file lands in raw/inbox/ or when the human says "ingest", "take in this source". Runs for
  both personal and codebase wikis (reads [wiki].profile).
id: a48953dd5b9343918a4cd50653e960f7
---

# LLM Wiki — Ingest

Turn raw sources into/updated concepts: keep provenance, don't break human content, and keep the search index in sync immediately.

Schema: `_schema.md`. Runbook: `AGENTS.md`. Related: `llm-wiki-base-query` (uses the knowledge), `llm-wiki-base-lint` + `llm-wiki-base-review` (verify afterwards), `llm-wiki-base-reindex` (index rebuild only).

## Overview

Reads a raw source from `raw/inbox/`, auto-detects domain, writes a summary source page + related entity/concept pages, updates `index.md` and `log.md`, runs incremental reindex, and moves the file out of inbox. Respects `active` pins and never sets `verified`. Works for both `personal` and `codebase` wiki profiles.

## Profile — read first

Read `[wiki].profile` in `<wiki_root>/.llm-wiki-base.toml`:

| | `personal` | `codebase` |
|---|---|---|
| wiki root | standalone wiki folder | `<project>/<wiki-dir>/` (e.g. `project-wiki/`) |
| touches per source | **10–15 pages** (wiki grows by topic) | **5–10 pages** (more focused) |
| typical domains | free-form by topic | `tech-stack`, `architecture`, `conventions`, `dependencies`, `deployment`, `testing`, `security`, `api`, `data-model`, `domain/<sub>` |
| content language | grammar/patterns + vocabulary must enter the wiki, not die in the source page | code paths must be **verified** before writing |

Marks **[personal]** / **[codebase]** below apply to that profile only.

## When

A new source lands in `raw/inbox/` — dropped by a human, produced by `scripts/extract_*.py`, OR **submitted by another AI via MCP `wiki_submit`** (docs, PRs, architecture notes, projects). The human says "ingest this".

## Workflow

1. **Read the source**: `read_raw_source(name, "inbox", wiki=<wiki name>)` or `wiki_read("raw/inbox/<name>", wiki=<wiki name>)`.
   - Wiki name: `llm-wiki-base wiki list`. `wiki=""` = cross-wiki (only when you genuinely need a source from another wiki).
   - Ambiguous content / not enough context to settle takeaways → `websearch` the URL or citation in the raw's `source` field before asking the human. **Never guess blind.**
2. **Discuss short takeaways with the human** (default: ingest one source at a time).
3. **Auto-detect domain** (top-level folder under `wiki/`):
   - Read content + URL + title → determine topic. Matching folder exists → use it.
   - None matches → create a new folder per the naming rule (kebab-case, lowercase, ASCII-safe) + empty `wiki/<domain>/index.md` (filled in step 7).
   - **[codebase]** Intent (requirements, decisions) ≠ observation (behavior read from code) — don't mix both in one page; unclear intent → record an open question, **don't invent requirements**.
4. **Write the summary page** → `wiki/<domain>/source/<slug>.md`.
   - REQUIRED frontmatter: `title`, `domain: <domain>`, `kind: source`, `sources`, `updated`, `status: active`, `generated: {by: "<tool>/<model>", at: <ISO-8601 with offset>}`.
   - **Do NOT set `verified`** — wait for human artifact review (`llm-wiki-base verify <path> --by <id>`; see `_schema.md` Trust tier).
   - `sources:` prefers list-of-dicts + per-claim citation. Flat list stays valid (legacy) when no per-claim citation is needed.
   - `sources:` rules: URL exists → `resource: <url>` (primary provenance). **NEVER** write `raw/inbox/...`. **NEVER** write `[[raw/inbox/...]]` in body.
   - **[codebase]** Body should reference code paths where applicable — inline code or wikilink.
   - **[personal]** Languages domain: grammar/patterns → dedicated concept pages; vocabulary → `wiki/<domain>/vocab/<slug>.md` table.
5. **Create/update related entity + concept pages** in the **same domain**, cross-linked `[[wiki/<domain>/...]]`.
   - **Anti-fork**: search DB for a `status: planned` page → **update** if found, don't create.
   - **Pins**: `active` pin on a section you're editing → do NOT overwrite. Contradiction → `wiki/alerts/`, **never revert silently**.
   - Every new page needs at least 1 outbound wikilink.
   - **[codebase]** kinds: `entity` = library/tool; `concept` = pattern/architecture; `source` = doc summary; `task` = task tracking.
6. **Auto-translation (if enabled)**: run `llm-wiki-base translate status` first. If `[translate].enabled = true` and `langs` non-empty: call **`llm-wiki-base-translate`** for each new page. `len(langs) > 5` or pages > 20 → warn before calling. `enabled = false` → skip silently.
7. Update `wiki/<domain>/index.md`. **New domain** → add row to `wiki/index.md`.
8. Insert into `wiki/log.md` (reverse-chronological): `## [YYYY-MM-DD HH:MM:SS] ingest | <title>`.
   - Date = `updated` from source page frontmatter. Use **Edit anchored at next entry** — **NEVER rewrite the whole file, NEVER `cat >>`**.
9. **Reindex** (incremental, inside `<wiki_root>`): `llm-wiki-base reindex`. `--check` = dry-run; `--full` when config changes.
10. **Move source**: `mv <wiki_root>/raw/inbox/<name> <wiki_root>/raw/<name>`.
11. **Verify**: `llm-wiki-base lint` or `wiki_search`. Report: concepts created/edited, reindexed, what **needs human review**.

## MCP tools (bridge for other AIs)

- Intake: `wiki_submit(title, content, wiki, domain, source)` → writes to `raw/inbox/`. Other AIs must NOT write `wiki/` directly.
- Read: `read_raw_source` · `wiki_read(path, wiki)` · `wiki_list(domain=…, kind=concept, wiki)`.
- Propose: `wiki_propose_edit(path, content, wiki)` → `wiki/.proposals/`. **`wiki` is mandatory on write.**
- **Indexing/ingesting is maintainer work via CLI**, NOT via MCP.

## Safety

- Writing wiki pages / index / log is re-derivable → agent writes directly. Any other claim needs provenance.
- **Raw is immutable** — never edit source files.
- **Never assume `tools/` lives inside the wiki root.** The `llm-wiki-base` CLI calls `~/.llm-wiki-base/` automatically. Always use the wrapper.
- **[codebase]** Code paths must be verified with `grep` before writing into the wiki.
- **[codebase]** Wiki ↔ code contradiction → flag the human, fix neither.
- Pages hold NO moveable values (SHA, mtime, counts). Never set `verified` on behalf of a human.
