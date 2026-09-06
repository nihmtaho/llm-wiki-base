---
name: llm-wiki-base-query
description: >
  Answer questions from ONE specific wiki (the one you stand in) — union retrieval (BM25 page ∪
  BM25 chunk ∪ vector chunk, RRF), LLM rerank, read the smallest sufficient page set, synthesize
  a cited answer, and file synthesis back as new pages. For searching ACROSS wikis, use
  `llm-wiki-base-research`.
---

# LLM Wiki — Query

Schema: `_schema.md`. Runbook: `AGENTS.md`. Related: `llm-wiki-base-reindex` (skewed index), `llm-wiki-base-lint` (structure), `llm-wiki-base-research` (cross-wiki).

## Boundary with `research`

| | `llm-wiki-base-query` (this skill) | `llm-wiki-base-research` |
|---|---|---|
| scope | **one** wiki, already known | many designated wikis / cross-wiki |
| `wiki=` | current wiki name (blank if it's the only one) | `""` or wiki list |
| outcome | answer + may **write** synthesis into the wiki | compare/contrast across wiki sources |

## When

The human asks about content already in the wiki.

## Process

1. **Structural routing**: read `wiki/index.md` → domain index (`wiki/<domain>/index.md`). Best route when the domain is known; skip if unclear.
   - **[codebase]** At a repo root with a project wiki, read `<wiki_root>/wiki/index.md` for domains (tech-stack, architecture, conventions, …).
2. **Pull a WIDER candidate pool than you'll read**:
   - `wiki_search(query, top_k = 2 × [retrieval].top_n_final, wiki=<wiki name>)` — union retrieval: BM25 page ∪ BM25 chunk ∪ vector chunk, fused by **RRF over rank**. Read `[retrieval]` in `.llm-wiki-base.toml`.
   - Vietnamese queries / special characters: the tool auto-relaxes (verbatim → AND sanitize → OR) when `relax_recall = true`.
   - `semantic_search(query, top_k, wiki)` to inspect the vector-chunk channel alone (exists only when `vector = true`).
   - Filter: `wiki_list(domain="…", kind="concept", wiki=…)`.
3. **RERANK HERE (the skill does it, not the tool)** — when `[retrieval].rerank = "llm"`:
   - Use only each candidate's `title` + `snippet` + `matched_by`; **do NOT open files** while scoring.
   - Criteria, in priority order:
     a. **Topical fit**, not just keyword overlap (off-meaning snippet → drop).
     b. More `matched_by` channels = more trustworthy (`bm25_page` + `bm25_chunk` + `vector_chunk` beats one channel).
     c. Trust tier: prefer `verified.by: human:*` > machine-confirmed > unverified.
     d. Same topic across pages → keep the canonical page (`concept`, not `source`/`index`).
   - Open exactly `[retrieval].top_n_final` pages (default 8). `rerank = "off"` → keep raw RRF order.
   - Why pool wide then cut: the tool ranks on statistical signals, but "does this page actually answer?" needs semantics — the LLM does that part better, as long as it doesn't burn tokens opening the wrong files.
4. **Read the selected pages** (`wiki_read`) for detail + provenance. Follow wikilinks to expand. **Chunks/snippets only *find* concepts — they are not answer content**; answers come from compiled pages (trust tier preserved).
5. **Synthesize a cited answer**: `[[wiki/<domain>/source/...]]` or URLs from `sources:`; cite Concept path + `[^id]` footnote when the page uses per-claim citation.
   - **[codebase]** Separate intent (`requirements`/decisions) from observation (behavior read from code) — never present an observation as a requirement.
6. **Trust-tier check** (both profiles): `status: draft` or no `verified` → flag "unverified" in the answer; past-`stale_after` (lint reports `stale-after-passed`) → flag stale; prefer human-reviewed.
   - **[codebase]** The wiki **can go stale against code**: cross-check critical claims with `grep` before concluding (codegraph plugin at the repo root first, if installed). Source priority: wiki → grep/find. **Don't jump straight to grep before checking the wiki** — the wiki was expensive to maintain, use it.
   - Contradiction between pages (or wiki vs code) → **report to the human**, never resolve or record an edge yourself.
7. Synthesis-worthy questions (comparisons, connections): **file back as a new page** in the fitting domain (`wiki/<domain>/concept/...`) + update the index → wiki compounding. New pages do NOT get `verified` — they await `llm-wiki-base verify`.
   - **[codebase]** Propose-only mode (not the maintainer): use `wiki_propose_edit` → `.proposals/` staging, awaiting `llm-wiki-base proposals apply`.
8. Not found → say so, propose ingest (`wiki_submit` into `raw/inbox/`) or web search. **Never fabricate.**

## Big tasks: research, then plan

Before a refactor / feature / multi-file change: run the process above for context, **then** enter plan mode (Shift+Tab), cite wiki pages in the plan, name gaps, and list pages to update after implementing. Every material claim in the plan needs a wiki path or URL; verification must be reproducible (MCP tool or shell command, not "try testing"). Plan contradicting the wiki → the wiki wins (it has provenance), flag the conflict to the human. Breaking changes → their own "Breaking:" section.

## Measuring retrieval quality

Run `llm-wiki-base eval` when: toggling `vector`, changing `chunk_tokens`/`fusion`, or the wiki clearly grows.

```bash
llm-wiki-base eval            # P@k / R@k / MRR under current config
llm-wiki-base eval --compare  # tier1-weighted / rrf-text / rrf+vector + verdict
llm-wiki-base eval --init     # create eval/golden.toml from template
```

- `--compare` is the **evidence** for `vector = true`, not a feeling.
- Goldens live in `eval/golden.toml` (commit). Source them from: real human questions across sessions, and questions the wiki got wrong (keep as regressions). **Don't let AI author queries for you** — then the numbers measure wiki↔AI overlap, not real usage.
- Results append to `eval/results.json` (gitignored) with a config fingerprint → comparable over time.
- `zero_recall_queries` = **wiki missing knowledge**, not a bad retriever → `llm-wiki-base-ingest`'s job.
- A channel vanishing from `matched_by` → check empty `chunks_fts` (`llm-wiki-base reindex --full`) or channel errors (eval prints `[ERROR] channel disabled by error`).

## MCP tools

Centralized server `llm-wiki-base-mcp` — each tool takes `wiki=`:
`wiki_search(query, top_k, wiki)` · `semantic_search(query, top_k, wiki)` · `wiki_read(path, wiki)` · `wiki_list(domain, kind, wiki)` · `wiki_lint(wiki)`.
Search/read results always carry a `wiki` field identifying their origin.

## Safety

- Never fabricate claims absent from wiki/raw; never infer beyond the wiki without marking it.
- Never cite volatile values as current truth (SHA, mtime, counts) — point at the live source.
- Cross-domain synthesis: a page spanning domains → goes to the domain the user cares about most, or a new domain.
- `wiki_submit` is the intake for **other AIs**, not for you while maintaining.
