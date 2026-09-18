---
name: llm-wiki-base-review
description: >
  Semantic (generative) check AFTER lint — contradictions between concepts, old claims, missing
  concepts, trust gaps, pin conflicts, stale/orphan diagrams, [codebase] stale code references +
  intent/observation drift → record gaps in wiki/alerts/. Cadence-gated by
  [review].interval_days. Run when the human says "review the wiki" or watch reports due.
id: 56fae0dfcc1b4cf09c30e055c30ae038
---

# LLM Wiki — Review

Principle: **deterministic first, generative second.** `llm-wiki-base-lint` handles structure and **must run before this skill** — lint fixes structural noise (broken wikilinks, missing indexes, DB skew, broken diagram refs) that would otherwise distort semantic analysis.

## Overview

Semantic health check after lint: finds contradictions, stale claims, missing concepts, trust gaps, pin conflicts, stale/missing diagrams, and (for codebase wikis) intent/observation drift. Records gaps in `wiki/alerts/` with evidence; never self-resolves anything. Cadence-gated by `[review].interval_days` to control cost.

## Cadence gate (cost control)

- Read watermark `wiki/.review_state.json` (`last_run`). Full run only past `[review].interval_days`; not due → skip, report "review not due".
- Deep pass (human says "deep review") runs unconditionally.
- **Scope cap**: cap `[review].max_pages` (default 80); over → recent + tag-neighbors only.
  - **[personal]** `concept/` + `source/`. **[codebase]** `entity/` + `concept/` + `source/`.

## Workflow

1. **Verify lint ran first.** If not, run `llm-wiki-base lint` before proceeding. Then pick candidates per scope. Read pages + `wiki/pins.yml` + `status: open` gaps in `wiki/alerts/` (+ code-path list from lint step 3 for codebase profile).
2. **Semantic check** — every gap needs **EVIDENCE**: verbatim quotes + related Concept IDs.
   - **Contradiction between concepts** — quote conflicting sentences from both sides.
   - **[codebase] Wiki ↔ code contradiction** — page says X, code does Y.
   - **[codebase] Stale code reference** — confirm with `grep`/`find`; flag if moved/deleted. **Never fix the page yourself.**
   - **Old claim** — past `stale_after` or superseded → surface, don't self-fix.
   - **Missing concept** — term mentioned often with no concept page → propose, don't create. Evidence threshold: ≥3 pages mention the term without linking to a concept page.
   - **[codebase] Intent–observation drift** — code observations frozen as implicit requirements with no intent source.
   - **Trust gap** — canonical concept `draft`/unverified too long → suggest `llm-wiki-base verify <path> --by <id>`.
   - **Pin conflict** — `active` pin contradicted by newer source → escalate to human.
   - **Stale diagram** — a Mermaid diagram in a concept or source page describes a flow/entity, but the surrounding text has been updated in ways that contradict the diagram's content (e.g., renamed nodes, removed steps). Flag as `stale-diagram` gap; never edit the diagram yourself.
   - **Missing diagram** *(ADVISORY)* — a concept describes a multi-step process or architecture with no diagram. Suggest adding one. Don't create diagrams yourself — flag for the human.
3. **Record gaps** in `wiki/alerts/<slug>.md`:
   - Frontmatter: `title`, `domain: alerts`, `kind: alert`, `status: open`, `last_seen: <YYYY-MM-DD>`, `sources` pointing at related concepts.
   - Body: evidence (verbatim quotes + `[[links]]`) + suggested questions / sources to find.
   - Existing gap (same topic + same slug) → bump `last_seen`, don't duplicate.
4. **Auto-close gaps**: an `open` gap NOT re-raised in the current pass (the same check type did not fire for that slug this run), AND `last_seen` is older than **two full cadence cycles** (i.e., `last_seen + 2 × interval_days < today`) → `status: closed`. NEVER close because it "looks fine" — only by the cadence rule or explicit human instruction.
5. **Update**: watermark `wiki/.review_state.json` = `{"last_run": "<ISO>", "gaps": <n>}`; append `wiki/log.md`.
6. Report: new / still-open / auto-closed gaps; diagram issues found; what needs a human decision.

## Don't

- **Don't mint concepts from thin evidence** — propose, human decides.
- Don't edit content / resolve contradictions yourself.
- Don't set/clear `verified` — `llm-wiki-base verify` is the human's command.
- Don't delete gap files — close with `status: closed` only.
- **Don't fabricate or rewrite Mermaid diagrams** — stale diagram → gap file, not a rewrite.
- **[codebase]** Don't conclude stale just because grep misses a path (aliases, re-exports, dynamic imports).
