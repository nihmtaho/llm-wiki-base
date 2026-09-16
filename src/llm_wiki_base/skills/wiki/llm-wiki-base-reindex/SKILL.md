---
name: llm-wiki-base-reindex
description: >
  Build / refresh the DERIVED search indexes from markdown: BM25 page + BM25 chunk + (optional)
  vector chunk. Incremental by content-hash; has dry-run and full rebuild. Use after ingest,
  when lint reports index skew, or after retrieval config changes. NEVER commit indexes.
id: b855ff1c504a47fb85004c4f1a6c9c18
---

# LLM Wiki — Reindex

Markdown is the source of truth; indexes are **derived** — throwable, rebuildable. This skill has one job: make the indexes match the markdown and the config.

## Overview

Runs `llm-wiki-base reindex` to sync BM25 page, BM25 chunk, and (optionally) vector chunk indexes against current markdown files. Checks config drift first, chooses incremental vs full rebuild, and confirms with numbers. Never commits indexes. Never enables vector without `eval --compare` evidence. Exposes `fusion = "weighted"` as a one-line rollback for unexpected RRF results.

## What's on disk

| component | location | built when |
|---|---|---|
| `pages_fts` (BM25 page) | `wiki/.wiki.db` | always |
| `chunks_fts` (BM25 chunk) | `wiki/.wiki.db` | **always** — independent of `vector` |
| vector chunks (`.json` + `.npy`) | `rag/.rag_index/` | only when `[retrieval].vector = true` |

Both chunk channels share **`tools/chunking.py`** (global runtime at `~/.llm-wiki-base/`) → same boundaries, so RRF between them is meaningful.

**Never indexed:** `wiki/index.md` + `wiki/log.md`, translations `*.<lang>.md`, frontmatter, verbatim footnotes.

## Modes

```bash
llm-wiki-base reindex            # incremental: only new/changed/deleted files by content-hash
llm-wiki-base reindex --check    # dry-run: what would index/delete, config drift, chunk-index state
llm-wiki-base reindex --full     # full rebuild — MANDATORY after changing chunk_tokens / embed_model / vector / fusion
```

## Rollback / A-B baseline

`fusion = "weighted"` in `.llm-wiki-base.toml` is the **one-line rollback**: replaces RRF with weighted-blend fusion. Use when RRF produces unexpected ranking and you want a stable A-B baseline before tuning. After switching `fusion`, run `--full` (different fingerprint = incomparable eval results).

## Vector channel gate

Only enable `[retrieval].vector = true` when `llm-wiki-base eval --compare` shows **measurable gain** (R@k or MRR). Enabling without evidence re-embeds the whole wiki, changes the config fingerprint, and adds an embed-model dependency that breaks on model change. Default to `vector = false`.

## Workflow

1. **Check state first** (no writes): `llm-wiki-base reindex --check`. Read: files to index/delete; config drift warning (→ `--full`); chunk-index state ("not built" = `bm25_chunk` dead).
2. **Run the right mode**:
   - No config change → `llm-wiki-base reindex`.
   - Changed `chunk_tokens` / `embed_model` / `vector` / `fusion` / `chunk_bm25` → `llm-wiki-base reindex --full`.
   - After `llm-wiki-base base install` upgrade that bumped `SCHEMA_VERSION` → `--full`.
3. **Confirm with numbers**:
   ```bash
   llm-wiki-base config show          # effective values ([env]/[toml]/[default])
   llm-wiki-base reindex --check      # must report 0 pending + no drift
   ```
   `chunks_fts` count must equal `rag/.rag_index/chunks.json` count when `vector = true`.
4. **Check dead channels**: `llm-wiki-base eval` prints `[ERROR] channel disabled by error` — distinguish config-disabled from broken.
5. Report: N pages indexed, chunks +/−, vector on/off, drift or not.

## Relations with other skills

- `llm-wiki-base-ingest` / `llm-wiki-base-consolidate` run incremental reindex as their final step.
- `llm-wiki-base-lint` only *detects* index skew; reindex *fixes* it.
- Config change → `--full` → re-measure with `llm-wiki-base eval --compare`.

## Don't

- Don't commit indexes (`.wiki.db`, `rag/.rag_index/`, `.env` are gitignored — never `git add -f`).
- Don't edit markdown while reindexing.
- Don't treat the index as truth — markdown wins on disagreement.
- Don't `--full` without a config change (re-embeds everything with `vector = true`).
- Don't enable `vector = true` without `eval --compare` evidence.
