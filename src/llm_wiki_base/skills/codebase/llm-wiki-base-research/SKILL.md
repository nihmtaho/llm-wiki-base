---
name: llm-wiki-base-research
description: >
  Research KNOWLEDGE across designated wikis (not inside a single wiki) —
  cross-wiki search via MCP `llm-wiki-base-mcp`, contrasting personal ↔ project wikis,
  falling back to grep when wikis lack it. Installed at the codebase ROOT (outside any
  wiki). Use when the answer may live in another wiki, or to learn what wikis exist on
  this machine.
---

# LLM Wiki — Research (cross-wiki)

## Boundary with `llm-wiki-base-query`

| | `llm-wiki-base-research` (this skill) | `llm-wiki-base-query` |
|---|---|---|
| scope | **many** designated wikis, or `wiki=""` = all | **one** wiki you stand in |
| installed at | `root_project/.agents/skills/` (codebase root) | `<wiki>/.agents/skills/` |
| purpose | find + contrast + decide which source to trust | answer + write synthesis into that wiki |
| write-back | only `wiki_submit` / `wiki_propose_edit` (staging) | may write pages + index + log (maintainer) |

If you already know which wiki holds the answer → use `llm-wiki-base-query`, don't go cross-wiki for nothing.

## Server & registry

`llm-wiki-base-mcp` is **one server for the whole machine**, reading `~/.llm-wiki-base/registry.toml` for known wikis:

```toml
[[wikis]]
name = "wiki-test"        # lookup key — use as the `wiki=` parameter
id   = "6f2a…"            # stable UUID — survives folder renames
path = "/Users/…/wiki-test"
type = "personal"         # personal | project
```

```bash
llm-wiki-base wiki list                      # names + types + paths + ids
llm-wiki-base wiki add <name> <path> --type personal
llm-wiki-base wiki remove <name>
```

**No `wiki=` in the registry ⇒ MCP can't see that wiki.** An unregistered wiki searches empty — that's not a retriever bug.

## When

- The question's home wiki is unclear ("how did I deploy X", "does this project already handle Y").
- Contrasting needed: the project wiki says A but the personal wiki (visible cross-wiki) already decided B.
- Before coding in a repo with a project wiki: learn stack / architecture / conventions.
- Deciding which knowledge bases exist on this machine and where to write.

## Process

1. **List wikis first** — `llm-wiki-base wiki list` (or MCP resource `registry://wikis`). Pick the search set; note each `type`.
2. **Search**:
   - Exactly 1 wiki → `wiki_search(query, top_k = 2 × top_n_final, wiki="<name>")`.
   - Many/unsure → `wiki_search(query, top_k, wiki="")` = cross-wiki; **every result carries a `wiki` field** — read it before citing, or you'll attribute personal knowledge to the project.
   - Union retrieval: BM25 page ∪ BM25 chunk ∪ vector chunk, fused by **RRF over rank**; a wiki with `vector = false` degrades to 2 text channels on its own, still runs.
3. **Rerank with your LLM** when `[retrieval].rerank = "llm"` (read each wiki's `.llm-wiki-base.toml` — config is per-wiki): score on `title` + `snippet` + `matched_by` only, do NOT open files; prefer (a) topical fit over word overlap, (b) multi-channel hits, (c) `verified.by: human:*`, (d) canonical pages (`concept`) over `source`/`index`; then cut to `top_n_final`.
4. **Read pages** (`wiki_read(path, wiki)`) — snippets/chunks only *pick* pages, they don't answer. Expand via wikilinks.
5. **Trust tier + profile check** before believing: `status: draft` / no `verified` → unverified; past `stale_after` → stale; a page from a **different-type wiki** (personal ↔ codebase) is *context*, not this repo's truth.
6. **[fallback] Wiki lacks it → search code/tech next:**
   1. wiki (`wiki_search`/`wiki_read`) — curated, provenanced, fast;
   2. `grep` / `find` — last resort.
   For project wikis we recommend the user install the codegraph plugin at the repo root (the agent picks it up when present) — call/import graphs navigate better than grep.
   **Don't jump straight to grep before checking the wiki.** The wiki was expensive to maintain — use it.
7. **Big task**: after researching → plan mode, cite `[[wiki/<domain>/kind/slug]]` (full path, never wrap a wikilink in a markdown link), name gaps explicitly, keep verification reproducible. A plan contradicting the wiki → the wiki wins (provenanced), flag the conflict. Breaking changes → their own "Breaking:" section.
8. **Not found** → say what's missing from the wiki, then propose intake (see write-back). Don't fabricate.

## Write-back (staging only — AI proposes, human decides)

| job | tool | target |
|---|---|---|
| submit new material | `wiki_submit(title, content, wiki, domain, source)` | `raw/inbox/` of the **human-designated** wiki |
| propose a page edit | `wiki_propose_edit(path, content, wiki)` | `wiki/.proposals/` → awaiting `llm-wiki-base proposals apply\|discard` |

- **`wiki` is mandatory on write.** Never pick the target wiki yourself; never infer it from content.
- **MCP doesn't ingest.** No tool writes `wiki/`, `index.md`, `log.md` directly, and no tool edits `.proposals` — review is CLI + human.

## Resources

`registry://wikis` (wiki list), `wiki://<name>/index` (top-level TOC), `wiki://<name>/log` (reverse-chronological history). Read `index` before searching when you don't know a wiki's domains yet.

## Safety

- **One centralized server, many wikis in one process.** Results always carry `wiki` + `path`; citations must name the source wiki. Don't use `wiki=""` when the question belongs to one wiki — cross-wiki mixes in personal-wiki results.
- **Project wiki ≠ personal wiki**, but cross-wiki search reads both → useful, and sources must be distinguished.
- **Wikis can go stale against code** → cross-check critical claims against code before concluding.
- **Contradictions** between wiki pages / wiki and code → report to the human, never self-resolve, never materialize a "new truth".
- Never cite another wiki's `raw/` as evidence for this repo — raw is local cache the user may delete; real provenance is the URL in `sources:`.
