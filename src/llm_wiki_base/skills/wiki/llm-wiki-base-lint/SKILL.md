---
name: llm-wiki-base-lint
description: >
  Health-check the DETERMINISTIC part of the wiki — orphans, broken wikilinks, frontmatter,
  timestamps, footnote↔sources, index sync, orphan pins, diagram integrity, layout.
  Contradictions / old claims / stale code references belong to `llm-wiki-base-review`. Run
  periodically or when the human says "lint the wiki".
id: 32357fa7610e45f39d0eeff6243b039e
---

# LLM Wiki — Lint

Principle: **deterministic first, generative second.** This skill covers structure only; semantics (contradictions, old claims, missing concepts, dead code paths) belong to `llm-wiki-base-review`. Always run lint **before** review — lint fixes structural noise that would otherwise inflate review results.

Schema: `_schema.md`. Runbook: `AGENTS.md`.

## Overview

Runs `llm-wiki-base lint` to detect structural issues, fixes re-derivable content (index entries, dangling DB rows, bad formats), checks diagram file integrity, and hands semantic gaps to `llm-wiki-base-review`. Never deletes pages or pins. Never touches semantics. Findings are classified by severity: CRITICAL → WARNING → ADVISORY.

## When

Periodically (`llm-wiki-base watch` runs it every `WATCH_LINT_SEC`) or when the human says "lint the wiki".

## Workflow

1. Run inside `<wiki_root>`:
   ```bash
   llm-wiki-base lint
   ```
   Returns `page_count`, `orphans`, `missing_file`, `findings` (each finding names its check and severity).
2. Handle each finding by severity:

   **CRITICAL** (blocks search — fix first):
   - **missing_file**: page in DB but file missing on disk → `llm-wiki-base lint --fix` (drops dangling DB rows).

   **WARNING** (structural gap — address in this pass):
   - **broken-wikilink**: `[[target]]` points at nonexistent file → fix the path or create the page.
   - **broken-diagram-ref**: `<!-- diagram: diagrams/<slug>-N.mmd -->` comment in a wiki page but the `.mmd` file is missing on disk → recreate from the fenced block in the page body, or remove the comment if the block was also removed. `.mmd` files are re-derivable.
   - **orphan-diagram**: a `.mmd` file exists in `wiki/<domain>/diagrams/` but no wiki page references it via a `<!-- diagram: ... -->` comment → report to human. **Do not delete** — the human decides whether to re-link or discard.
   - **missing-frontmatter**: missing `title`/`domain`/`kind` → backfill (infer from path).
   - **status-vocab**: `status`/`confidence` outside vocab → fix (vocab in `_schema.md`).
   - **timestamp-format**: `updated` not `YYYY-MM-DD`, offset fields not ISO-8601 → fix.
   - **stale-after-passed**: `stale_after` elapsed → report to human, **do NOT change status yourself**.
   - **footnote-sources-match**: `[^id]` not matching `sources[].id` → fix citation or sources.
   - **missing-index-entry** / **domain-missing-index**: `llm-wiki-base lint --fix` — auto-adds entries + creates `index.md`.
   - **pin-orphan**: pin lost its anchor → report to human, **never delete pins yourself**.
   - **orphan** (no inbound `[[link]]`): find related pages to link from, or record as intentional.
   - **`sources-no-local-path`** / **body-no-raw-inbox-wikilink**: drop references to `raw/inbox/`.

   **ADVISORY** (fix when touching that page; governed by `[lint]` in `.llm-wiki-base.toml`):
   - **dense-bullet / indent-depth / banned-terms**: style guidelines — don't hold up the pass.

3. **[codebase] Collect code paths** (input for review, NO verdicts here):
   - Extract every code path referenced in `entity/` + `concept/` pages.
   - Check existence via `grep`/`find`/`ls` → list {path, referencing page, alive/dead}.
   - Hand the list to `llm-wiki-base-review`. **Don't edit pages in lint.**
4. **Sync indexes**:
   ```bash
   llm-wiki-base reindex
   ```
   Incremental. `--check` = dry-run; `--full` on config change. `.mmd` files and `*.<lang>.md` translation files are automatically excluded from indexing — lint does not need to handle them. Detail: `llm-wiki-base-reindex` skill.
5. **Hand semantics to review**: contradictions, old claims, missing concepts, trust gaps, stale diagrams → `llm-wiki-base-review`. **No semantics here.**

## MCP tools

`wiki_lint(wiki)` · `wiki_list(domain, kind, wiki)` · `wiki_read(path, wiki)` · `wiki_search(query, wiki)`.

## Safety

- Lint only reports + auto-fixes the **re-derivable**: index entries, dangling DB rows, formats, broken-diagram-ref (from page body).
- **Never delete pages** (even orphans), never delete pins, never touch `wiki/.proposals/`.
- **Never delete `.mmd` diagram files** — even orphaned ones. Report them; the human decides.
- **[codebase]** Code-staleness checks are heuristics — confirm with human before updating pages.
