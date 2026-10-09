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

# 2. In the wiki root: re-sync skills + schema templates (.agents/skills/,
#    AGENTS.md, _schema.md come from the new core; same -c as your original init)
llm-wiki-base init personal --force        # project wiki: llm-wiki-base init project --force

# 3. Build the links table — required, once
llm-wiki-base reindex --full

# 4. Optional: see what the new checks find
llm-wiki-base lint
```

Notes:

- **Step 3 is mandatory once**: incremental reindex only extracts links for
  content-hash-changed pages, so an untouched wiki gets an empty `links` table
  without `--full`.
- Tag-registered wikis can fold steps 1–2 into one backed-up operation:
  `llm-wiki-base upgrade --dry-run` → `llm-wiki-base upgrade --to latest`
  (details: [upgrading.md](upgrading.md)). Then still run step 3.
- **Language-focused wiki?** Opt into a pack — add to `.llm-wiki-base.toml`:

  ```toml
  [langpack]
  enabled = true
  pack = "japanese"
  ```

  then `llm-wiki-base lint`. Everything else stays off-by-default; a wiki without
  `[langpack]` has zero behavior change. See [langpacks.md](langpacks.md).
