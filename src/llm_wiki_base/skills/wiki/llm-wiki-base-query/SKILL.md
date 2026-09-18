---
name: llm-wiki-base-query
description: >
  Answer questions from ONE specific wiki (the one you stand in) — union retrieval (BM25 page ∪
  BM25 chunk ∪ vector chunk, RRF), LLM rerank, read the smallest sufficient page set, synthesize
  a cited answer, and file synthesis back as new pages. For searching ACROSS wikis, use
  `llm-wiki-base-research`.
id: ec781179122e4767b0abeae0500b8044
---

# LLM Wiki — Query

Schema: `_schema.md`. Runbook: `AGENTS.md`. Related: `llm-wiki-base-reindex` (skewed index), `llm-wiki-base-lint` (structure), `llm-wiki-base-research` (cross-wiki).

## Overview

Single-wiki question answering: read `index.md` for routing, pull a wide candidate pool via union retrieval (BM25 page ∪ BM25 chunk ∪ vector chunk, RRF), LLM-rerank on metadata only (no file opens during scoring), open `top_n_final` pages, synthesize a cited answer, and file synthesis-worthy answers back as new concept pages. For cross-wiki queries, use `llm-wiki-base-research`.

## Boundary with `research`

| | `llm-wiki-base-query` (this skill) | `llm-wiki-base-research` |
|---|---|---|
| scope | **one** wiki, already known | many designated wikis / cross-wiki |
| `wiki=` | current wiki name (blank if it's the only one) | `""` or wiki list |
| outcome | answer + may **write** synthesis into the wiki | compare/contrast across wiki sources |

## When

The human asks about content already in the wiki.

## Workflow

1. **Structural routing**: read `wiki/index.md` → domain index (`wiki/<domain>/index.md`). For small wikis, `index.md` alone is often sufficient — use it before searching. Skip if domain is unclear.
   - **[codebase]** Read `<wiki_root>/wiki/index.md` for domains (tech-stack, architecture, conventions, …).
2. **Pull a WIDER candidate pool than you'll read**:
   - `wiki_search(query, top_k = 2 × [retrieval].top_n_final, wiki=<wiki name>)` — union retrieval: BM25 page ∪ BM25 chunk ∪ vector chunk, fused by **RRF over rank**.
   - `semantic_search(query, top_k, wiki)` to inspect the vector-chunk channel alone (only when `vector = true`).
   - Filter: `wiki_list(domain="…", kind="concept", wiki=…)`.
   - **Diagram-aware queries**: if the query is about a process, flow, or architecture, prefer pages that contain `mermaid` fenced blocks (they appear in BM25 results via body text). Mermaid content is indexed as part of the page body — no separate diagram search is needed. Only read a `.mmd` file directly (via `wiki_read`) when the wiki page refers to it with `<!-- diagram: ... -->` and you need the raw diagram code for editing/output.
3. **RERANK (the skill does it, not the tool)** — when `[retrieval].rerank = "llm"`:
   - Use only `title` + `snippet` + `matched_by`; **do NOT open files** while scoring.
   - Priority: (a) topical fit over keyword overlap; (b) multi-channel hits; (c) `verified.by: human:*` > unverified; (d) `concept` over `source`/`index`.
   - Open exactly `[retrieval].top_n_final` pages (default 8). `rerank = "off"` → keep raw RRF order.
4. **Read selected pages** (`wiki_read`) for detail + provenance. Follow wikilinks. **Snippets only *find* pages — answers come from compiled pages.**
5. **Synthesize a cited answer**: `[[wiki/<domain>/source/...]]` or URLs from `sources:`; cite `[^id]` footnotes.
   - **[codebase]** Separate intent (requirements/decisions) from observation — never present observation as requirement.
   - If the answer involves a process or flow that has a Mermaid diagram in the source pages, include the Mermaid fenced block in your answer verbatim — don't fabricate new diagrams.
6. **Trust-tier check**: `status: draft` or no `verified` → flag "unverified"; past `stale_after` → flag stale.
   - **[codebase]** Cross-check critical claims with `grep` before concluding. **Don't jump to grep before checking the wiki.**
   - Contradiction between pages → **report to human**, never resolve yourself.
7. Synthesis-worthy answers → **file back as new page** in `wiki/<domain>/concept/...` + update index. A synthesis answer is worth filing when it: (a) draws on 3+ pages, (b) would take a search to reconstruct, and (c) doesn't duplicate an existing concept page. New pages do NOT get `verified`. Do NOT copy Mermaid blocks from source pages into synthesis pages unless the diagram accurately represents the synthesized concept — if uncertain, omit the diagram and note "see source diagrams."
   - **[codebase]** Propose-only mode: use `wiki_propose_edit` → `.proposals/`.
8. Not found → say so, propose ingest. **Never fabricate.**

## Big tasks: research, then plan

Before a refactor / feature / multi-file change: run query for context, then plan mode (Shift+Tab). Cite wiki pages in the plan. Plan contradicting the wiki → wiki wins, flag the conflict. Breaking changes → their own "Breaking:" section.

## Measuring retrieval quality

Run `llm-wiki-base eval` when toggling `vector`, changing `chunk_tokens`/`fusion`, or the wiki grows. If search consistently misses, `llm-wiki-base eval --compare` is the diagnostic — not config tuning by feel.

```bash
llm-wiki-base eval            # P@k / R@k / MRR under current config
llm-wiki-base eval --compare  # tier1-weighted / rrf-text / rrf+vector + verdict
```

- `--compare` is the **evidence** for `vector = true` and fusion changes. Unexpected RRF ranking → try `fusion = "weighted"` as an A-B baseline first.
- `zero_recall_queries` = wiki missing knowledge → `llm-wiki-base-ingest`.
- Channel vanishing from `matched_by` → `llm-wiki-base reindex --full` or check `[ERROR]` in eval output.

## MCP tools

`wiki_search(query, top_k, wiki)` · `semantic_search(query, top_k, wiki)` · `wiki_read(path, wiki)` · `wiki_list(domain, kind, wiki)` · `wiki_lint(wiki)`.

## Safety

- Never fabricate claims absent from wiki/raw.
- Never cite volatile values (SHA, mtime, counts) — point at the live source.
- Never fabricate Mermaid diagrams — only embed diagrams that exist verbatim in source pages.
- `wiki_submit` is for **other AIs' intake**, not for you while maintaining.
