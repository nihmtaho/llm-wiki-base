---
name: llm-wiki-lint
description: >
  Health-check the DETERMINISTIC part of the wiki — orphans, broken wikilinks, frontmatter,
  timestamps, footnote↔sources, index sync, orphan pins, layout. Contradictions / old claims /
  stale code references belong to `llm-wiki-review`. Run periodically or when the human says
  "lint the wiki".
---

# LLM Wiki — Lint

Principle: **deterministic first, generative second.** This skill covers structure only; semantics (contradictions, old claims, missing concepts, dead code paths) belong to `llm-wiki-review`.

Schema: `_schema.md`. Runbook: `AGENTS.md`.

## When

Periodically (`llm-wiki watch` runs it every `WATCH_LINT_SEC`) or when the human says "lint the wiki".

## Process

1. Run inside `<wiki_root>`:
   ```bash
   llm-wiki lint
   ```
   Returns `page_count`, `orphans`, `missing_file`, `findings` (each finding names its check).
2. Handle each finding type:
   - **broken-wikilink**: `[[target]]` points at a nonexistent file → fix the path or create the page.
   - **missing-frontmatter**: missing frontmatter / missing `title`/`domain`/`kind` → backfill (infer from path).
   - **status-vocab**: `status`/`confidence` outside vocab → fix (vocab in `_schema.md`, incl. `planned`/`deprecated`/`superseded`).
   - **timestamp-format**: `updated` not `YYYY-MM-DD`, `stale_after`/`verified.at`/`generated.at` not offset ISO-8601 → fix the format.
   - **stale-after-passed**: `stale_after` elapsed → report to the human, **do NOT change status yourself**.
   - **footnote-sources-match**: `[^id]` not matching `sources[].id` (or vice versa) → fix the citation or the sources.
   - **missing-index-entry** / **domain-missing-index**: `llm-wiki lint --fix` — auto-adds missing entries (additive) + creates `index.md` for domains lacking one.
   - **pin-orphan**: a pin in `wiki/pins.yml` lost its concept/anchor → report to the human, **never delete pins yourself**.
   - **orphan** (page with no inbound `[[link]]`): find related pages to link from, or record as intentional.
   - **missing_file**: page in DB but file missing on disk → `llm-wiki lint --fix` (drops dangling rows).
   - **`sources-no-local-path`** / **body-no-raw-inbox-wikilink**: drop references to `raw/inbox/`.
   - **dense-bullet / indent-depth / banned-terms**: advisory — fix when touching that page (`[lint]` in `.llm-wiki.toml`).
3. **[codebase] Collect code paths** (input for review, NO verdicts here):
   - Extract every code path / filename referenced in `entity/` + `concept/` pages.
   - Check existence with `grep`/`find`/`ls` → list {path, referencing page, alive/dead}.
   - Hand the list to `llm-wiki-review` for the stale verdict. **Don't edit pages in lint** — this is a heuristic, not truth.
4. **Sync indexes (DB + chunk index)**:
   ```bash
   llm-wiki reindex
   ```
   Incremental by content-hash. `--check` = dry-run (reports what would index/delete + config drift + chunk-index state); `--full` on config change. Detail: `llm-wiki-reindex` skill.
5. **Hand semantics to review**: contradictions, old claims vs newer sources, missing concepts, trust gaps, **[codebase]** stale-code verdicts → `llm-wiki-review` skill (cadence `[review].interval_days`). **No semantics here.**

## MCP tools

`wiki_lint(wiki)` · `wiki_list(domain, kind, wiki)` · `wiki_read(path, wiki)` · `wiki_search(query, wiki)`.

## Safety

- Lint only reports + auto-fixes the **re-derivable**: index entries, dangling DB rows, formats.
- Semantic decisions belong to the human (via the review skill).
- **Never delete pages**, even orphans — the human decides. Never delete pins. Never touch `wiki/.proposals/` (that's `llm-wiki proposals`' job).
- **[codebase]** Code-staleness checks are heuristics — confirm with the human before updating pages.
