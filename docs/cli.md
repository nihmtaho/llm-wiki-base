# CLI reference

Full command reference for `llm-wiki`. Start with the [README](../README.md)
quickstart; concepts (two-layer architecture, authority tiers) are there.

## Global runtime

```bash
llm-wiki base install              # → ~/.llm-wiki-base/ (default)
llm-wiki base install --force      # recreate venv + reinstall requirements
llm-wiki base path                 # print current base dir
```

## Setup

```bash
llm-wiki setup                                     # interactive wizard

# Personal
llm-wiki setup personal --name "My Knowledge" --lang vi
llm-wiki setup personal -c claude -c commandcode   # MCP clients (repeatable)
llm-wiki setup personal --no-mcp                   # skip MCP
llm-wiki setup personal --no-register              # skip registry.toml (tests/scripts)
llm-wiki setup personal --skills-target claude     # + symlink .claude/skills/
llm-wiki setup personal --no-skills                # skip skill install

# Project
llm-wiki setup project -c claude -c opencode
llm-wiki setup project --wiki-dir project-wiki     # subfolder holding the wiki
llm-wiki setup project --lang vi
llm-wiki setup project --server-name my-wiki-mcp   # rename centralized server
llm-wiki setup project --no-register               # keep tests from dirtying the registry
```

Accepted clients: `claude`, `opencode`, `zed`, `commandcode`. Setup writes the
MCP entry (`llm-wiki-base-mcp`) into the **per-project/personal wiki MCP file**
(`.mcp.json` for claude/commandcode, `opencode.jsonc` for opencode — inside the
wiki/repo itself, committable to VCS). Clients without a project-scope file
(e.g. `zed`) are reported as skipped. Setup **prints the file path + key** it
wrote so you know exactly what changed.

## Wiki management (registry)

```bash
llm-wiki wiki list
llm-wiki wiki add my-wiki /path/to/wiki --type personal
llm-wiki wiki remove my-wiki            # accepts name or id; deletes no files
```

Each wiki has a `name` (human-readable lookup key — used as the `wiki=`
parameter) and an `id` (machine-generated UUID, stable). Same `name`, different
path → setup **auto-suffixes `-<uuid8>`** instead of silently evicting the old
wiki from the registry. MCP's `wiki=` accepts both.

## Per-wiki operations (cwd = wiki dir)

```bash
llm-wiki wiki ingest raw/inbox/foo.md    # index 1 source into search DB (writes no pages)
llm-wiki wiki reindex                    # incremental by content-hash (+ chunks_fts)
llm-wiki wiki reindex --check            # dry-run: what would index/drop + config drift + chunk index state
llm-wiki wiki reindex --full             # full rebuild (after embed_model/chunk_tokens/vector/fusion changes)
llm-wiki check lint                       # deterministic health-check (orphans, broken links, frontmatter, …)
llm-wiki check lint --fix                 # delete dangling rows + add missing index entries (additive)
llm-wiki check eval                       # P@k / R@k / MRR on golden queries (read-only)
llm-wiki check eval --compare             # tier1-weighted / rrf-text / rrf+vector + vector verdict
llm-wiki check eval --init                # create eval/golden.toml from template
llm-wiki review list             # pending proposals + diff size
llm-wiki review show <name>      # metadata + unified diff vs current page
llm-wiki review apply <name> [--by <human-id>]   # write page + log + reindex + delete proposal
llm-wiki review discard <name> --force
llm-wiki review new -t wiki/x/y.md -f body.md    # create a proposal from CLI
llm-wiki config show                # effective config, each key marked [default]/[toml]/[env …]
llm-wiki check verify wiki/<d>/concept/x.md --by <human-id>
llm-wiki check verify <path> --unverify
llm-wiki watch                      # daemon: inbox → ingest → reindex → lint (+ review-due nudges)
llm-wiki setup doctor                     # environment check + CLI ↔ AI-tool boundary
```

**`llm-wiki setup doctor`** checks: base runtime exists; `tools/` in base matches the
package file-by-file (prompts `llm-wiki base install` on drift); base-venv deps
(`mcp`, `fastembed`, and `tomli` only on venv < 3.11); registry (ghost path →
FAIL, wiki missing `id` → WARN); current wiki (has `.llm-wiki.toml`, has
`[wiki].profile`, registered or not, stale proposals); finally a table of the
**6 jobs that require an AI tool**. FAIL → exit 1, WARN → still 0.

## Upgrade / status

```bash
llm-wiki status                 # core local/latest tags + VERSION per wiki
llm-wiki upgrade --dry-run      # preview only
llm-wiki upgrade --to latest [--wiki <name>]
llm-wiki upgrade --to v0.2.0 --wiki my-wiki
```

Details: [upgrading.md](upgrading.md).

## Translation

```bash
llm-wiki translate enable --lang vi --lang ja   # written to .llm-wiki.toml (comments kept)
llm-wiki translate status                       # show state
llm-wiki translate disable                      # off, langs kept
llm-wiki translate check --lang vi              # verify frontmatter + heading sync
```

Details: [translation.md](translation.md).

## Config (`.llm-wiki.toml`)

Behavior config per wiki, **committed** to the wiki repo. Precedence:
**env > TOML > default.**

```toml
[wiki]
profile = "personal"      # personal | codebase — set by setup; skills read it for mode
lang = "en"               # language the agent WRITES pages in (not translation target)

[retrieval]
fusion = "rrf"            # "weighted" = legacy behavior: one-line rollback, also the A-B baseline
chunk_bm25 = true         # BM25 channel over semantic chunks
vector = true             # on by default (measured); off unless your own wiki's eval shows Δ>0
rerank = "llm"            # skill-layer rerank — Python never reads this key
chunk_tokens = 512        # only matters when a section exceeds it (measured: no-op on short wikis)
top_k_bm25 = 20           # candidates per text channel
top_k_vector = 20         # candidates, vector channel
top_n_final = 8           # final results + skill reading budget
relax_recall = true       # keep → AND sanitize → single OR retry (CJK-safe)

[retrieval.weights]       # RRF is only sensitive to RATIOS
bm25_page = 1.0
bm25_chunk = 1.0
vector = 1.0

[retrieval.index]
embed_model = ""          # empty = builtin

[models]                  # SKILL-LAYER CONTRACT — Python calls no LLM, reads none of this
light = ""                # model for WRITE (concept generation)
heavy = ""                # model for VERIFY/review
provider = ""             # openai-compatible | anthropic | ollama; empty = use the AI tool's LLM
api_key_env = ""          # NAME of the env var holding the key — never write keys into files

[eval]
k = 8                     # cutoff for `llm-wiki check eval`

[review]
interval_days = 7         # review skill only runs full past this mark
max_pages = 80

[lifecycle]
default_stale_after_days = 180

[lint]
banned_terms = []
```

Changing `embed_model` / `chunk_tokens` / `vector` / `fusion` → run
`llm-wiki wiki reindex --full`. Runtime plumbing (paths) still goes through `.env` +
env vars.

`chunk_tokens` and `rrf_k` are **measured no-ops** on small wikis: 256/512/1024
give identical chunk counts when every section is short, and an `rrf_k` sweep of
20→250 produced identical numbers. Don't touch them until your own wiki's eval
says otherwise.

`llm-wiki setup` never overwrites an existing `.llm-wiki.toml` (only patches a
missing `[wiki]`), and every command writing this file (`translate enable`,
`setup` profile) **preserves comments** — comments here are documentation, not
decoration.

Env overrides: `WIKI_EMBED_MODEL`, `WIKI_FUSION`, `WIKI_CHUNK_BM25`,
`WIKI_BM25_WEIGHT`, `WIKI_VEC_WEIGHT` (last two only apply when
`fusion = "weighted"`). The installer does **not** pin retrieval env into the
MCP entry — pinning there would disable `.llm-wiki.toml` inside MCP only
(env > TOML) while the CLI still reads it, i.e. the same wiki returning two
different results.
