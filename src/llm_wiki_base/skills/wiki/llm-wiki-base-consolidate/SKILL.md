---
name: llm-wiki-base-consolidate
description: >
  Merge the log layer and scattered fragments into canonical concepts — in-place merge, additive,
  re-grounded from raw, distill-verified (citations must not shrink). Runs periodically or when
  the human says "consolidate", "merge topics".
id: 02d0ac9295a542b9a174935958169683
---

# LLM Wiki — Consolidate

Turn time-ordered entries (`log.md`, duplicate source pages) into canonical per-concept knowledge, without losing evidence and without self-serving hallucination.

## Overview

Merges scattered wiki fragments and log entries into canonical per-concept pages. Additive only — never deletes, never loses citations, never touches human-pinned sections. One topic per run; always ends with an incremental reindex and a report.

## Immutable principles

- **Raw → concept only.** Never regenerate a concept from another concept. Every merged claim must trace to a source (`sources[]` pointing at a URL / `raw/` / source page).
- **Additive merge.** Existing content is immutable; merging only *adds*. Never rewrite/delete old content except deliberate deprecation.
- **Single source per fact.** Two concepts holding the same fact → pick the canonical one, mark the other `status: superseded` + `x_supersedes: <canonical-path>`, leave a pointer (**never delete the file**).
- **Pins** (`wiki/pins.yml`): whatever section an `active` pin anchors → that section is immutable. Missing section / pin contradicted by a newer source → push to `wiki/alerts/`, **never revert silently**.

## When

- The human says "consolidate" or "merge topics".
- Runs periodically when `llm-wiki-base watch` detects log growth or many scattered fragments on the same topic.
- After multiple ingest sessions have produced overlapping source pages on a shared topic.
- **One topic per run.** Many pending topics → pick the highest-priority one, complete its reindex + report, then stop. Don't batch multiple topics in one pass.

## Workflow

1. Read the watermark `wiki/.consolidate_state.json` (`last_entry` — the previous log mark, avoids reprocessing).
2. **Pick candidates**: new `wiki/log.md` entries since the watermark + topics with information scattered across pages (human-named topic wins on priority).
   - **[codebase]** Prefer topics where many `entity`/`source` pages mention the same pattern — that's a missing-canonical-concept signal.
3. Per topic → determine the **target canonical concept** (`wiki/<domain>/concept/<slug>.md`). None exists → create per schema; honor `status: planned` anti-fork (see `_schema.md`).
4. **Re-ground**: gather material from source/raw (**never from another concept**); every merged claim needs a `[^id]` citation matching `sources[].id`.
5. **Merge in place (additive)** into the target concept — keep the body structured, path-style wikilinks.
6. **Re-check pins** after merging: still holding → keep; contradicted → `wiki/alerts/`; section gone → orphan (report to the human).
7. **Distill-verify**: the concept's `[^id]` citation set after merging must **not shrink** vs before — count before/after, print in the report. Every new claim needs a source.
8. **Trust**: judgment-changing content → `llm-wiki-base verify <path> --unverify` to drop `verified` (awaits human re-review). **Never set `verified` yourself.**
9. **Update**: fresh frontmatter `generated: {by, at}`; re-describe `wiki/<domain>/index.md` if needed; deprecate duplicates (`x_supersedes`); append `wiki/log.md` (`## [<ISO8601>] consolidate | <topic>` — insert in reverse-chronological order, Edit with anchor, never rewrite the whole file); advance the watermark; run `llm-wiki-base reindex` (incremental — the CLI wrapper resolves the global runtime automatically; never reference `tools/` inside the wiki).
10. **Report**: which concepts merged, which deprecated, citations before/after, what needs human review.

## Don't

- Don't shrink/lose citations. Don't delete human content. Don't raise `verified` for the human.
- Don't delete concept files — deprecate + pointer only.
- Don't merge past one topic per run (see "When" above).
