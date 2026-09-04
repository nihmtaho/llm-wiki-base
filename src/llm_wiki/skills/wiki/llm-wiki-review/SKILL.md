---
name: llm-wiki-review
description: >
  Semantic (generative) check AFTER lint — contradictions between concepts, old claims, missing
  concepts, trust gaps, pin conflicts, [codebase] stale code references + intent/observation
  drift → record gaps in wiki/alerts/. Cadence-gated by [review].interval_days. Run when the
  human says "review the wiki" or watch reports due.
---

# LLM Wiki — Review

Principle: **deterministic first, generative second.** `llm-wiki-lint` handles structure (runs FIRST); this skill handles what needs understanding.

## Cadence gate (cost control)

- Read the watermark `wiki/.review_state.json` (`last_run`). Full run only past `[review].interval_days` (`.llm-wiki.toml`); not due → deterministic skip (~0s), report "review not due".
- Deep pass (human explicitly says "deep review") runs unconditionally.
- **Input scope**: recent pages + tag-neighbors — cap `[review].max_pages` (default 80); over → recent + tag-neighbors only. Skip when nothing changed since last time.
  - **[personal]** scope = `concept/` + `source/`. **[codebase]** scope = `entity/` + `concept/` + `source/`.

## Process

1. Pick candidates per the scope above. Read pages + `wiki/pins.yml` + `status: open` gaps in `wiki/alerts/` (plus the code-path list handed over by `llm-wiki-lint` step 3, for the codebase profile).
2. **Semantic check** — every gap needs **EVIDENCE**: verbatim quotes + related Concept IDs.
   - **Contradiction between concepts** — quote the conflicting sentences from both sides.
   - **[codebase] Wiki ↔ code contradiction** — the page says X, the code does Y.
   - **[codebase] Stale code reference** — for each referenced code path: confirm with `grep`/`find`; moved/deleted path → flag stale. **Never fix the page yourself.** Stale checks are heuristics → the final verdict belongs to the human.
   - **Old claim** — past `stale_after`, or superseded by a newer source → surface, don't self-fix.
   - **Missing concept** — a term mentioned often with no concept page of its own → propose, don't create.
   - **[codebase] Intent–observation drift** — code observations "frozen" into implicit requirements with no intent source confirming them.
   - **Trust gap** — canonical concept sitting `draft`/unverified too long → suggest human review: `llm-wiki verify <path> --by <id>`.
   - **Pin conflict** — an `active` pin contradicted by a newer source (from ingest/consolidate) → escalate to the human.
3. **Record gaps** in `wiki/alerts/<slug>.md`:
   - Frontmatter: `title`, `domain: alerts`, `kind: alert`, `status: open`, `last_seen: <YYYY-MM-DD>`, `sources` pointing at related concepts.
   - Body: evidence (verbatim quotes + `[[links]]`) + suggested questions to investigate / sources to find.
   - Gap already exists (same topic) → bump `last_seen` to today, don't duplicate.
4. **Auto-close gaps**: an `open` gap NOT re-raised this pass with `last_seen` missing **two consecutive cadences** → `status: closed`. NEVER close because it "looks fine".
5. **Update**: watermark `wiki/.review_state.json` = `{"last_run": "<ISO>", "gaps": <n>}`; append `wiki/log.md` (`## [<ISO8601>] review | <N> gaps`).
6. Report: new / still-open / auto-closed gaps, and what needs a human decision.

## Don't

- **Don't mint concepts from thin evidence** — propose, the human decides.
- Don't edit content / resolve contradictions for the human — surface with evidence only.
- Don't set/clear `verified` — `llm-wiki verify` is the human's command.
- Don't delete gap files — close with `status: closed` only.
- **[codebase]** Don't conclude stale just because grep misses a path (aliases, re-exports, dynamic imports).
