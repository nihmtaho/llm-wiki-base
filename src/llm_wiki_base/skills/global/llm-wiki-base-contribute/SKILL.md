---
name: llm-wiki-base-contribute
description: >
  Create a markdown page following the llm-wiki-base wiki schema (frontmatter,
  domain, kind, sources, wikilinks, trust tiers) and stage it into one or more
  target wikis via MCP. Use when asked to "contribute to the wiki", "add knowledge
  to the wiki", "create a wiki page", "propose a wiki page", or when new knowledge
  needs to enter a wiki. Select the target wiki(s) at skill start — the human must
  designate which wiki receives the contribution.
# Cursor (.mdc / rule) — on-demand, triggered by request, not file
alwaysApply: false
globs: ["wiki/**/*.md", "raw/**/*.md"]
# Windsurf
trigger: llm-wiki-base-contribute
# Kiro
inclusion: fileMatch
fileMatchPattern: "wiki/**"
# GitHub Copilot (.github/instructions/*.instructions.md)
applyTo: "wiki/**/*.md"
---

# LLM Wiki — Contribute

Create a properly-formatted wiki page that follows the llm-wiki-base schema and
contribute it to a target wiki chosen by the human. This skill is the entry point
for adding **new knowledge** to a wiki — distinct from `llm-wiki-base-ingest`, which
processes a raw source file already staged in `raw/inbox/`.

Schema reference: `_schema.md` (at the wiki root). Runbook: `AGENTS.md`.

Related skills:
- `llm-wiki-base-ingest` — processes a raw source in `raw/inbox/` into wiki pages
- `llm-wiki-base-query` — answers questions from a wiki
- `llm-wiki-base-lint` — structural health check
- `llm-wiki-base-review` — semantic health check (contradictions, staleness)
- `llm-wiki-base-reindex` — rebuilds search DB + RAG

## Profile — read first

The wiki `[wiki].profile` determines domain conventions:

| | `personal` | `codebase` |
|---|---|---|
| wiki root | standalone folder | `<project>/<wiki-dir>/` (e.g. `project-wiki/`) |
| typical domains | free-form by topic | `tech-stack`, `architecture`, `conventions`, `dependencies`, `deployment`, `testing`, `security`, `api`, `data-model`, `domain/<sub>` |
| `entity` kind | frameworks, tools, people, orgs | libraries, frameworks, deps, tools |
| `concept` kind | concepts, patterns, theory | patterns, architecture, layers |

Marks **[codebase]** / **[personal]** below apply to that profile only.

## When to use this skill

- Asked to "contribute to the wiki", "add knowledge to the wiki", "create a wiki page"
- New knowledge needs to enter a wiki (no raw source file in `raw/inbox/`)
- Asked to "propose a wiki page" or "stage a wiki edit"

**Do NOT use this skill when:**
- A raw source file has landed in `raw/inbox/` → use `llm-wiki-base-ingest`
- Asked a question about existing wiki content → use `llm-wiki-base-query`
- Asked to fix a structural issue in existing pages → use `llm-wiki-base-lint`

## Process

### 1. Select the target wiki(s)

The human **must** designate which wiki receives the contribution. List available
wikis:

```bash
llm-wiki-base wiki list
```

Or via MCP: `wiki_list(wiki="")` lists pages across all wikis.

Ask the human to pick **one or more** target wikis. Every MCP write tool requires
`wiki=<name>` — never stage content into a wiki the human did not designate.

### 2. Search for existing coverage (anti-fork)

Before creating a page, search the target wiki to check if the topic already exists.
This prevents fork/duplication:

```bash
wiki_search(query="<topic>", wiki=<target>, top_k=10)
wiki_list(domain="", kind=concept|entity|source, wiki=<target>)
```

- If a `status: planned` placeholder exists on the topic → **update** it, don't create.
- If an active page covers the topic → propose edits to the existing page via
  `wiki_propose_edit`, don't fork.
- Only create a new page if the topic is genuinely absent.

### 3. Determine page kind and domain

**Kind** = semantic role of the content:

| `kind` | Use for |
|---|---|
| `source` | Summary of an external resource (doc, article, PR, session note) |
| `concept` | Concepts, patterns, architecture, theory |
| `entity` | Frameworks, libraries, tools, people, organizations |
| `task` | Task tracking (only in domains with task tracking) |
| `alert` | Review gaps, contradictions, staleness (pseudo-domain `alerts`) |

**Domain** = top-level folder under `wiki/`. Naming rule: kebab-case, lowercase,
ASCII-safe. Match an existing domain when one fits; create a new folder + empty
`index.md` only when the topic is genuinely separate.

- **[codebase]** Intent (requirements, decisions) ≠ observation (behavior read from
  code) — don't mix both in one page.
- **[personal]** Languages domain: grammar/patterns → `concept` pages; vocabulary →
  `wiki/<domain>/vocab/<slug>.md`.

### 4. Create the markdown page

Follow the `_schema.md` frontmatter contract exactly:

```yaml
---
title: "..."                          # REQUIRED
domain: <domain>                     # REQUIRED — top-level folder name
kind: source|concept|entity|task|alert  # REQUIRED
sources:                             # REQUIRED — provenance
  - id: s1
    resource: <url-or-wiki-xref-or-raw-path>
    title: "..."
updated: YYYY-MM-DD                 # REQUIRED
status: draft                        # draft | active | done | stale | planned | deprecated | superseded
tags: [db, infra]                   # optional, inline list
generated: {by: "<tool>/<model>", at: 2026-09-01T09:00:00+07:00}  # recommended
# verified: {by: "human:<id>", at: <ISO-8601>}  # NEVER set yourself
stale_after: 2027-01-01T00:00:00+07:00  # optional — when content expires
x_owner: "human:<id>"               # optional
---
```

**Body rules:**

- First line is a **TL;DR** sentence.
- Structured markdown with headings (`#` main, `##` sections).
- Every material claim needs provenance: a `[[wiki page]]` link in the body **or**
  a URL in `sources:`.
- Per-claim citation footnotes with **verbatim quotes**:
  ```markdown
  Important takeaway.[^s1]

  [^s1]: Resource title
      > [human:<id>] "exact verbatim quote from the source"
  ```
- Wikilinks, full-path only: `[[wiki/<domain>/<kind>/<slug>]]`. Custom text via
  `[[path|Text]]`. **Never** wrap in markdown links.
- **Never set `verified`** — that is the human's job
  (`llm-wiki-base verify <path> --by <human-id>`). Pages you create start as
  `status: draft` + `generated` (no `verified`), which means **unverified**.
- **[codebase]** Body should reference code paths where applicable
  (`src/auth/middleware.ts`, `tests/auth.test.ts`) — inline code or wikilink.

**Anti-fork before create** (re-read step 2): check for an existing `status: planned`
placeholder on the same topic → update it, don't create a new page.

### 5. Stage the contribution

Choose the MCP staging tool based on intent:

**`wiki_submit`** — for new source documents (external content to be ingested):
```
wiki_submit(title, content, wiki=<target>, domain=<domain>, source=<url>)
```
Writes to `raw/inbox/<slug>.md` with auto frontmatter. The `llm-wiki-base-ingest`
skill must run afterward to turn it into proper wiki pages.

**`wiki_propose_edit`** — for proposing a fully-formatted wiki page:
```
wiki_propose_edit(path="wiki/<domain>/<kind>/<slug>.md", content=<full markdown>, wiki=<target>)
```
Stages to `wiki/.proposals/` as a human-gated edit. The human reviews and applies:
```bash
llm-wiki-base review apply <name> --by <human-id>
```

**Never write `wiki/` pages directly** — MCP only stages to `raw/inbox/` or
`.proposals/`. The `llm-wiki-base-ingest` skill and the human maintainer are the
only ones who write canonical `wiki/` pages.

### 6. Verify

After staging:
```bash
llm-wiki-base wiki reindex && llm-wiki-base check lint
```

Report: what was staged, to which wiki, and what human review is needed.

## MCP tools (bridge for other AIs)

Centralized server `llm-wiki-base-mcp` — each tool takes `wiki=`:

- **Search existing**: `wiki_search(query, top_k, wiki)`, `semantic_search(query, top_k, wiki)`,
  `wiki_list(domain, kind, wiki)`, `wiki_read(path, wiki)`
- **Stage new source**: `wiki_submit(title, content, wiki, domain, source)` → `raw/inbox/`
- **Propose wiki page**: `wiki_propose_edit(path, content, wiki)` → `wiki/.proposals/`
- **Health check**: `wiki_lint(wiki)`

Search/read results always carry a `wiki` field identifying their origin.

## Safety

- **Raw is staging** — `wiki_submit` only writes to `raw/inbox/`. The human must
  confirm before `llm-wiki-base-ingest` pulls it into the wiki.
- **Proposals are human-gated** — `wiki_propose_edit` stages to `.proposals/`,
  never writes `wiki/` directly.
- **AI proposes, human decides** — never set `verified`; never overwrite human pins
  in `wiki/pins.yml`. A new source contradicting a pin → record an alert in
  `wiki/alerts/`, never revert silently.
- **Provenance required** — every claim needs a `[[wiki page]]` link or URL in
  `sources:`. Never cite `raw/inbox/` paths in `sources:` (staging, path drifts).
- **Path safety** — paths are confined to the target wiki root; traversal outside
  is blocked by the MCP server.
- **[codebase]** Code paths must be verified: before writing `src/foo/bar.ts` into
  the wiki, confirm the file exists via `grep`. A wiki stale on code paths is the
  worst project-wiki failure.
- **Never fabricate** — claims without evidence go to `wiki/alerts/` as open questions,
  not as asserted facts.
