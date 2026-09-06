# Upgrading

## Tag-based upgrade (current)

Every wiki registered in `registry.toml` upgrades to a GitHub tag (`vX.Y.Z`):

```bash
llm-wiki-base status                 # core local/latest tags + VERSION per wiki
llm-wiki-base upgrade --dry-run      # preview: which files change, per wiki
llm-wiki-base upgrade --to latest    # backup → sync → stamp VERSION
llm-wiki-base upgrade --to v0.2.0 --wiki my-wiki
```

What one apply does, per wiki:

1. Backs up managed files (`.agents/skills/`, `AGENTS.md`, `_schema.md`,
   `.claude/CLAUDE.md`) into `.llm-wiki-base/backups/<timestamp>/` (keeps 5).
2. Re-runs the same installers `init` uses (overwrite + prune shipped-away
   skills via `.agents/skills/.llm-wiki-base-skills.json`; your own skills kept).
3. Stamps the tag into `.llm-wiki-base/VERSION`.

Project wikis additionally re-sync the `codebase` skill (`llm-wiki-base-research`,
…) at the project root (nearest ancestor holding it), with its own backup +
`VERSION` under the same timestamp.

Safety rules:

- Apply refuses when the running core is not checked out at the target tag and
  prints the `git fetch && git checkout` instructions (files always come from
  the running core — no silent mix).
- `latest` only ever matches **stable** tags; betas are tried via explicit
  checkout (see skill `llm-wiki-base-release`).
- Rollback = `upgrade --to <older-tag>` (core checked out there first) or copy
  back from `.llm-wiki-base/backups/<ts>/`.

## Migrating from pre-tag versions

```bash
pip install -e . && llm-wiki-base base install           # 1. sync code → ~/.llm-wiki-base/
cd <old-wiki> && llm-wiki-base reindex --full             # 2. build chunks_fts + fix FTS duplicate rows
cd <old-wiki> && llm-wiki-base init personal -c claude    # 3. refresh skills + MCP (answer yes)
llm-wiki-base doctor                                     # 4. see what's left
```

- Step 2 is one-time mandatory: incremental skips content-hash-unchanged pages,
  so an old wiki never gets chunks without `--full`.
- **Merged + renamed skills**: 13 personal/project skills → 8 profile-aware
  `llm-wiki-base-*`. Re-init **deletes** old `wiki-project-*` and keeps your own
  skills. Project wikis additionally get `llm-wiki-base-research` at the **repo
  root**.
- **`vector = true`** became the new-template default. Old wikis stay `false`
  until you `eval --compare`; enabling needs `reindex --full` to build
  `rag/.rag_index`.
- Registry gained **`id` (UUID)**; `init`/`wiki add` assign it automatically.
  Same-name-different-path no longer silently evicts.
- `--no-register` (and env `LLM_WIKI_BASE_REGISTRY`) keeps tests off the real registry.
- `wiki_search` ranking **changed** (RRF replaces weighted sum). Legacy
  behavior: `fusion = "weighted"` — one line, and the A-B baseline.
- `semantic_search` no longer returns `index.md`/`log.md` chunks (deliberate).
- Old code still opens new DBs fine (only new code reads `chunks_fts`).
- `llm-wiki-base proposals …` is new for `.proposals/`; old proposals need explicit
  `apply --target <path>`.

**Old wiki layout** (with `tools/`, `rag/`, `scripts/`, `.venv/` inside the wiki):

```bash
llm-wiki-base base install
cd /path/to/old-wiki && rm -rf tools/ rag/ scripts/ .venv/
llm-wiki-base reindex          # wrapper uses the global base
```
