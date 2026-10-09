# Migrating a wiki to typed relations

What changed for running wikis:

- New **`links`** table (typed relations) — DB `SCHEMA_VERSION` 3 → 4.
- New lint rules for relations/claims (`broken-relation-target`,
  `unknown-rel-type`, `claim-without-footnote`, …) — they only fire on pages that
  actually declare relations or a `## Claims` section, so untouched pages produce
  no new findings.
- Optional `[langpack]` config (off by default).

**No content changes required.** Old pages stay valid — plain wikilinks keep
producing default `related` edges, and there is no backfill pass: add
`relations:` / `## Claims` incrementally whenever consolidate or review already
touches a page (see [relations.md](relations.md)).

## Steps

```bash
# 1. Update the core (pick your install — see README) + sync the global runtime
uv tool install --force "git+https://github.com/nihmtaho/llm-wiki-base.git"  # uv tool
#   local clone instead: git pull && pip install -e .[dev]
llm-wiki-base setup tools

# 2. Re-sync the wiki's managed files from the new core (backups first)
llm-wiki-base upgrade --dry-run        # preview: which files change
llm-wiki-base upgrade --to latest      # backup → overwrite skills + AGENTS.md + _schema.md

# 3. In the wiki root — build the links table (required, once)
llm-wiki-base reindex --full

# 4. Optional: see what the new checks find
llm-wiki-base lint
```

Notes:

- **Step 2 is the sync mechanism.** Mirroring [upgrading.md](upgrading.md):
  `upgrade` first backs up the managed files (`.agents/skills/`, `AGENTS.md`,
  `_schema.md`, `.claude/CLAUDE.md`) into `.llm-wiki-base/backups/<timestamp>/`
  (keeps 5), then re-runs the installers with **overwrite** (pruning
  shipped-away skills; your own skills kept). This is what delivers the new
  `_schema.md` **Relations & Claims** section. The wiki must be in the registry —
  check `llm-wiki-base wiki list`, register `llm-wiki-base wiki add <name> <path>`.
  Safety rules (running core checked out at the target tag, rollback) live in
  [upgrading.md](upgrading.md).
- `llm-wiki-base init personal|project` only **creates** a wiki: it installs
  skills into a fresh dir but never overwrites an existing `AGENTS.md` /
  `_schema.md` — it is not a sync path for an existing wiki.
- **Step 3 is mandatory once**: incremental reindex only extracts links for
  content-hash-changed pages, so an untouched wiki gets an empty `links` table
  without `--full`.
- **Language-focused wiki?** Opt into a pack — add to `.llm-wiki-base.toml`:

  ```toml
  [langpack]
  enabled = true
  pack = "japanese"
  ```

  then `llm-wiki-base lint`. Everything else stays off-by-default; a wiki without
  `[langpack]` has zero behavior change. See [langpacks.md](langpacks.md).
