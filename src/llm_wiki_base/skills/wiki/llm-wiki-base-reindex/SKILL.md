---
name: llm-wiki-base-reindex
description: >
  Build / refresh the DERIVED search indexes from markdown: BM25 page + BM25 chunk + (optional)
  vector chunk. Incremental by content-hash; has dry-run and full rebuild. Use after ingest,
  when lint reports index skew, or after retrieval config changes. NEVER commit indexes.
---

# LLM Wiki — Reindex

Markdown is the source of truth; indexes are **derived** — throwable, rebuildable. This skill has one job: make the indexes match the markdown and the config.

## What's on disk

| component | location | built when |
|---|---|---|
| `pages_fts` (BM25 page) | `wiki/.wiki.db` | always |
| `chunks_fts` (BM25 chunk) | `wiki/.wiki.db` | **always** — independent of `vector` |
| vector chunks (`.json` + `.npy`) | `rag/.rag_index/` | only when `[retrieval].vector = true` |

Both chunk channels share **`tools/chunking.py`** → same boundaries, so RRF between them is meaningful.

**Never indexed:** `wiki/index.md` + `wiki/log.md` (reserved), translations `*.<lang>.md`, frontmatter, verbatim footnotes (verbatim evidence — indexed, every keyword query would score phantom hits).

## Modes

```bash
llm-wiki-base reindex            # incremental (default): only new/changed/deleted files by content-hash
llm-wiki-base reindex --check    # dry-run: reports what would index/delete, config drift, chunk-index state
llm-wiki-base reindex --full     # full rebuild — MANDATORY after changing chunk_tokens / embed_model / vector / fusion
```

Run inside `<wiki_root>`. The `watch` daemon auto-reindexes on mtime every `WATCH_REINDEX_SEC` — so this skill is for when you want results **now** or need to debug.

## Process

1. **Check state first** (writes nothing): `llm-wiki-base reindex --check`. Read:
   - files to index / to delete;
   - **config drift** — a "config changed since last reindex" warning means `--full`, not incremental;
   - **chunk index** — "not built" means the `bm25_chunk` channel is dead and search runs on 2 channels.
2. **Run the right mode**:
   - No config change → `llm-wiki-base reindex`.
   - Changed `chunk_tokens` / `embed_model` / `vector` / `fusion` / `chunk_bm25` → `llm-wiki-base reindex --full`. Why full: incremental skips pages whose content-hash didn't change, so an old wiki would **never** gain chunks without force.
   - First run after a `llm-wiki-base base install` upgrade that bumped `SCHEMA_VERSION` → `--full` (that's what the version bump is for, not decoration).
3. **Confirm with numbers**, not feelings:
   ```bash
   llm-wiki-base config show          # EFFECTIVE values (env overrides applied, tagged [env]/[toml]/[default])
   llm-wiki-base reindex --check      # must report 0 pending files + no drift
   ```
   `chunks_fts` chunk count must **equal** the chunk count in `rag/.rag_index/chunks.json` when `vector = true` — a mismatch means the two channels disagree on boundaries (a bug, not a config).
4. **Check dead channels**: `llm-wiki-base eval` (with `eval/golden.toml` present) prints `[ERROR] channel disabled by error` — distinguish "disabled by config" from "disabled by breakage".
5. Report: N pages indexed, chunks +/−, vector on/off, drift or not.

## Relations with other skills

- `llm-wiki-base-ingest` / `llm-wiki-base-consolidate` run **incremental** reindex for just-changed parts as their final step.
- `llm-wiki-base-lint` only *detects* index skew; `reindex` *fixes* it.
- Changing `chunk_tokens`/`embed_model`/toggling `vector` ⇒ `--full`, then **re-measure** with `llm-wiki-base eval --compare` (old numbers are incomparable — different fingerprint).

## Don't

- Don't commit indexes: `.wiki.db`, `rag/.rag_index/`, `.env` are already in the wiki's `.gitignore`. Never `git add -f` them.
- Don't edit markdown while reindexing — the index is one-directional (md → index).
- Don't treat the index as truth: index vs markdown disagree → **markdown is right**.
- Don't `--full` rebuild "to be safe" without a config change — with `vector = true` it re-embeds everything (model + GPU/CPU cost), and a changed fingerprint breaks comparability.
