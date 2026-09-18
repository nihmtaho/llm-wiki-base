---
name: llm-wiki-base-ingest
description: >
  Feed one raw source into the wiki and integrate it as concepts — auto-detect domain, read,
  summarize, cross-link entity/concept, embed/extract Mermaid diagrams into knowledge pages,
  update index/log, incremental reindex. Use when a new file lands in raw/inbox/ or when the
  human says "ingest", "take in
  this source". Runs for both personal and codebase wikis (reads [wiki].profile).
id: a48953dd5b9343918a4cd50653e960f7
---

# LLM Wiki — Ingest

Turn raw sources into/updated concepts: keep provenance, don't break human content, embed Mermaid diagrams directly into knowledge pages (concept/entity), and keep the search index in sync immediately.

Schema: `_schema.md`. Runbook: `AGENTS.md`. Related: `llm-wiki-base-query` (uses the knowledge), `llm-wiki-base-lint` + `llm-wiki-base-review` (verify afterwards), `llm-wiki-base-reindex` (index rebuild only).

## Overview

Reads a raw source from `raw/inbox/`, auto-detects domain, writes a summary source page + related entity/concept pages, and handles Mermaid diagrams in two ways: **non-special diagrams are embedded inline directly into the relevant concept/entity knowledge pages**; special (standalone/architectural) diagrams are additionally extracted as `.mmd` files. Updates `index.md` and `log.md`, runs incremental reindex, and moves the file out of inbox. Respects `active` pins and never sets `verified`. Works for both `personal` and `codebase` wiki profiles.

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
   - If the source content appears already fully covered in the wiki → tell the human and stop; don't create duplicate pages.
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
   - **Mermaid diagrams**: if the source contains ` ```mermaid ` fenced blocks, apply the [Mermaid Diagram Ingestion](#mermaid-diagram-ingestion) sub-workflow after writing the page.
   - Keep all fenced blocks verbatim in the source page body regardless of which path (non-special or special) the diagram takes.
5. **Create/update related entity + concept pages** in the **same domain**, cross-linked `[[wiki/<domain>/...]]`.
   - **Anti-fork**: search DB for a `status: planned` page → **update** if found, don't create.
   - **Pins**: `active` pin on a section you're editing → do NOT overwrite. Contradiction → `wiki/alerts/`, **never revert silently**.
   - Every new page needs at least 1 outbound wikilink.
   - **Mermaid in knowledge pages**: for every diagram classified as **non-special** in step 4, embed it inline in the most relevant concept/entity page (the knowledge file). This is the default — embed unless the diagram is special. See [Non-special path](#non-special-inline-path) below.
   - **[codebase]** kinds: `entity` = library/tool; `concept` = pattern/architecture; `source` = doc summary; `task` = task tracking.
6. **Auto-translation (if enabled)**: run `llm-wiki-base translate status` first. If `[translate].enabled = true` and `langs` non-empty: call **`llm-wiki-base-translate`** for each new page. `len(langs) > 5` or pages > 20 → warn before calling. `enabled = false` → skip silently. **`.mmd` files are never translated** — skip them.
7. Update `wiki/<domain>/index.md`. **New domain** → add row to `wiki/index.md`. Include diagram count: if diagrams were created, append `(+N diagrams)` to the domain index row for this source page.
8. Insert into `wiki/log.md` (reverse-chronological): `## [YYYY-MM-DD HH:MM:SS] ingest | <title>`.
   - Date = `updated` from source page frontmatter. Use **Edit anchored at next entry** — **NEVER rewrite the whole file, NEVER `cat >>`**.
9. **Reindex** (incremental, inside `<wiki_root>`): `llm-wiki-base reindex`. `--check` = dry-run; `--full` when config changes. `.mmd` files are excluded from indexing automatically.
10. **Move source**: `mv <wiki_root>/raw/inbox/<name> <wiki_root>/raw/<name>`.
11. **Verify**: `llm-wiki-base lint` or `wiki_search`. Report: concepts created/edited, diagrams extracted (list `.mmd` paths), reindexed, what **needs human review**.

## Mermaid Diagram Ingestion

Apply this sub-workflow whenever the source body contains one or more ` ```mermaid ` fenced blocks (detected during step 4). The **first decision** for each block is: is it special or not?

### Classification: special vs. non-special

Classify each `mermaid` block **before** deciding how to handle it:

| Signal | Classification |
|---|---|
| Describes a **single** concept/entity (one flow, one component, one state machine) | **Non-special → inline** |
| Simple diagram type: flowchart, sequence, state, class, ER for one entity | **Non-special → inline** |
| Spans **multiple** concepts/domains, is a system-level architecture diagram | **Special → `.mmd`** |
| Source labels it as a primary/standalone diagram (e.g. title "System Architecture") | **Special → `.mmd`** |
| Likely to be cross-referenced from **3+ pages** | **Special → `.mmd`** |
| Could not be clearly attributed to a single concept/entity page | **Special → `.mmd`** |

**Default when uncertain: non-special (inline).** Only use the special path when at least one "special" signal is clearly present. The goal is to get diagrams into concept/entity knowledge pages by default.

---

### Non-special (inline) path

For each block classified as **non-special** (this is the common case):

1. **Keep the fenced block verbatim** in the source page body (no comment marker needed).
2. **Identify the target knowledge page**: the concept or entity page that this diagram most directly describes. If it doesn't exist yet, create it as part of step 5.
3. **Embed the fenced block inline** in that knowledge page at the most logical position (after the introductory paragraph, before or within the relevant section).
4. **Add a provenance comment** directly above the block in the knowledge page:
   ```
   <!-- diagram derived from: wiki/<domain>/source/<source-slug>.md -->
   ```
5. **No `.mmd` file** is created. No `<!-- diagram: ... -->` marker in the source page.

If the same diagram logically belongs to **more than one** concept/entity page → embed in the primary page; add a cross-reference wikilink in the secondary pages pointing to the primary.

---

### Special (standalone) path

For each block classified as **special**:

1. **Save as** `wiki/<domain>/diagrams/<source-slug>-N.mmd` (0-indexed N) — create `wiki/<domain>/diagrams/` if it doesn't exist.
2. **Content**: the raw Mermaid code only (no fences, no surrounding markdown).
3. **In the source page body**: keep the fenced block verbatim, then add a trailing comment on the next line:
   ```
   <!-- diagram: diagrams/<source-slug>-N.mmd -->
   ```
   This comment lets `llm-wiki-base-lint` verify the `.mmd` file exists (broken-diagram-ref check).
4. **Embed in concept/entity pages** (same as non-special step 3–4 above): copy the fenced block inline into the most relevant knowledge pages, with `<!-- diagram derived from: ... -->`. Don't wikilink to `.mmd` from within concept pages — the inline block is the readable form; `.mmd` is the asset.

### Immutability and re-ingestion

- **Non-special diagrams**: re-ingestion → update the inline block in the knowledge page. If the block changed, overwrite in place.
- **Special diagrams** (`.mmd`): re-derivable from the source page. Re-ingestion → **overwrite** the `.mmd` files — never append.
- Raw source is still immutable — only the extracted `.mmd` (wiki side) changes.
- If the source has no diagrams, skip this entire sub-workflow silently.

### What NOT to do

- **Never translate** Mermaid syntax — it's code, not natural language.
- **Never index** `.mmd` files — the ingest CLI automatically excludes them.
- **Never** put diagram file paths under `raw/` — diagrams are wiki-side artifacts, not raw.

## MCP tools (bridge for other AIs)

- Intake: `wiki_submit(title, content, wiki, domain, source)` → writes to `raw/inbox/`. Other AIs must NOT write `wiki/` directly.
- Read: `read_raw_source` · `wiki_read(path, wiki)` · `wiki_list(domain=…, kind=concept, wiki)`.
- Propose: `wiki_propose_edit(path, content, wiki)` → `wiki/.proposals/`. **`wiki` is mandatory on write.**
- **Indexing/ingesting is maintainer work via CLI**, NOT via MCP.

## Safety

- Writing wiki pages / index / log is re-derivable → agent writes directly. Any other claim needs provenance.
- **Raw is immutable** — never edit source files.
- **Never assume `tools/` lives inside the wiki root.** The `llm-wiki-base` CLI calls `~/.llm-wiki-base/` automatically. Always use the wrapper.
- **Mermaid/`.mmd` files are wiki-side only** — re-derivable, never committed to raw, never translated, never indexed.
- **[codebase]** Code paths must be verified with `grep` before writing into the wiki.
- **[codebase]** Wiki ↔ code contradiction → flag the human, fix neither.
- Pages hold NO moveable values (SHA, mtime, counts). Never set `verified` on behalf of a human.
