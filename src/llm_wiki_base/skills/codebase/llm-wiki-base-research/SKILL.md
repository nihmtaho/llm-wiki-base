---
name: llm-wiki-base-research
description: >
  Research KNOWLEDGE across designated wikis (not inside a single wiki) —
  cross-wiki search via MCP `llm-wiki-base-mcp`, contrasting personal ↔ project wikis,
  falling back to grep when wikis lack it. Installed at the codebase ROOT (outside any
  wiki). Use when the answer may live in another wiki, or to learn what wikis exist on
  this machine.
id: 6683c23ef53449c499b22e1d6d9c68e6
---

# LLM Wiki — Research (cross-wiki)

## Overview

Cross-wiki knowledge search via the centralized `llm-wiki-base-mcp` server. Installed at the codebase ROOT (not inside any wiki). Lists wikis first, searches with `wiki=""` for cross-wiki or a named wiki when known, LLM-reranks on metadata, reads pages, checks trust tiers, and falls back to `grep` only as a last resort. Write-back is staging only (`wiki_submit` / `wiki_propose_edit`) — AI proposes, human decides.

## Boundary with `llm-wiki-base-query`

| | `llm-wiki-base-research` (this skill) | `llm-wiki-base-query` |
|---|---|---|
| scope | **many** designated wikis, or `wiki=""` = all | **one** wiki you stand in |
| installed at | `root_project/.agents/skills/` (codebase root) | `<wiki>/.agents/skills/` |
| purpose | find + contrast + decide which source to trust | answer + write synthesis into that wiki |
| write-back | staging only (`wiki_submit` / `wiki_propose_edit`) | may write pages + index + log (maintainer) |

**Decision rule**: if you already know which wiki holds the answer, use `llm-wiki-base-query` — don't go cross-wiki for nothing. Use research when: (a) the home wiki is unclear, (b) contrasting personal ↔ project knowledge is needed, or (c) you don't know what wikis exist yet.

## Server & registry

`llm-wiki-base-mcp` is **one server for the whole machine**, reading `~/.llm-wiki-base/registry.toml`:

```bash
llm-wiki-base wiki list                      # names + types + paths + ids
llm-wiki-base wiki add <name> <path> --type personal
llm-wiki-base wiki remove <name>
```

**No `wiki=` in the registry ⇒ MCP can't see that wiki.** An unregistered wiki searches empty — not a retriever bug.

## When

- The question's home wiki is unclear.
- Contrasting needed: project wiki says A, personal wiki already decided B.
- Before coding in a repo with a project wiki: learn stack / architecture / conventions.
- Deciding which knowledge bases exist on this machine.

## Workflow

1. **List wikis first** — `llm-wiki-base wiki list` (or MCP resource `registry://wikis`). Note each `type`. Read `wiki://<name>/index` for an unknown wiki's domain map before searching.
2. **Search**:
   - Exactly 1 wiki → `wiki_search(query, top_k = 2 × top_n_final, wiki="<name>")`.
   - Many/unsure → `wiki_search(query, top_k, wiki="")` = cross-wiki; **every result carries a `wiki` field** — read it before citing.
   - Union retrieval: BM25 page ∪ BM25 chunk ∪ vector chunk, fused by RRF; `vector = false` wiki degrades to 2 text channels.
3. **Rerank** when `[retrieval].rerank = "llm"` (per-wiki config): score on `title` + `snippet` + `matched_by` only — do NOT open files. Prefer: (a) topical fit, (b) multi-channel hits, (c) `verified.by: human:*`, (d) `concept` over `source`/`index`. Cut to `top_n_final`.
4. **Read pages** (`wiki_read(path, wiki)`) — snippets only pick pages. Expand via wikilinks.
5. **Trust tier check**: `status: draft` / no `verified` → unverified; past `stale_after` → stale; different-type wiki (personal ↔ codebase) = context only, not this repo's truth.
6. **[fallback]** Wiki lacks it → `grep`/`find`. Don't jump to grep before checking the wiki.
7. **Big task**: plan mode after research; cite `[[wiki/<domain>/kind/slug]]` (full path, never wrap in markdown link); flag wiki vs plan contradictions. Breaking changes → their own "Breaking:" section.
8. **Not found** → say what's missing, propose intake. Don't fabricate.

## Write-back (staging only)

| job | tool | target |
|---|---|---|
| submit new material | `wiki_submit(title, content, wiki, domain, source)` | `raw/inbox/` of the human-designated wiki |
| propose a page edit | `wiki_propose_edit(path, content, wiki)` | `wiki/.proposals/` → `llm-wiki-base proposals apply\|discard` |

- **`wiki` is mandatory on write.** Never pick the target wiki yourself.
- **MCP doesn't ingest.** No tool writes `wiki/`, `index.md`, `log.md` directly.

## Resources

`registry://wikis` · `wiki://<name>/index` · `wiki://<name>/log`.

## Safety

- Results always carry `wiki` + `path`; citations must name the source wiki.
- Don't use `wiki=""` when the question belongs to one wiki.
- Contradictions → report to human, never self-resolve.
- Never cite another wiki's `raw/` as evidence for this repo.
