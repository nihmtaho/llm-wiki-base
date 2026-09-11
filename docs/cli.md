# CLI reference

Full command reference for `llm-wiki-base`. Start with the [README](../README.md)
quickstart; concepts (two-layer architecture, authority tiers) are there.

## Global runtime

```bash
llm-wiki-base version                   # print installed package version
llm-wiki-base base install              # → ~/.llm-wiki-base/ (default)
llm-wiki-base base install --force      # recreate venv + reinstall requirements
llm-wiki-base base path                 # print current base dir
```

## Setup

```bash
llm-wiki-base setup                                     # interactive wizard

# Personal
llm-wiki-base setup personal --name "My Knowledge" --lang vi
llm-wiki-base setup personal -c claude -c commandcode   # MCP clients (repeatable)
llm-wiki-base setup personal --no-mcp                   # skip MCP
llm-wiki-base setup personal --no-register              # skip registry.toml (tests/scripts)
llm-wiki-base setup personal --skills-target claude     # + symlink .claude/skills/
llm-wiki-base setup personal --no-skills                # skip skill install

# Project
llm-wiki-base setup project -c claude -c opencode
llm-wiki-base setup project --wiki-dir project-wiki     # subfolder holding the wiki
llm-wiki-base setup project --lang vi
llm-wiki-base setup project --server-name my-wiki-mcp   # rename centralized server
llm-wiki-base setup project --no-register               # keep tests from dirtying the registry
```

Accepted clients: `claude`, `opencode`, `zed`, `commandcode`. Setup writes the
MCP entry (`llm-wiki-base-mcp`) into the **per-project/personal wiki MCP file**
(`.mcp.json` for claude/commandcode, `opencode.jsonc` for opencode — inside the
wiki/repo itself, committable to VCS). Clients without a project-scope file
(e.g. `zed`) are reported as skipped. Setup **prints the file path + key** it
wrote so you know exactly what changed.

## Wiki management (registry)

```bash
llm-wiki-base wiki list
llm-wiki-base wiki add my-wiki /path/to/wiki --type personal
llm-wiki-base wiki remove my-wiki            # accepts name or id; deletes no files
```

Each wiki has a `name` (human-readable lookup key — used as the `wiki=`
parameter) and an `id` (machine-generated UUID, stable). Same `name`, different
path → setup **auto-suffixes `-<uuid8>`** instead of silently evicting the old
wiki from the registry. MCP's `wiki=` accepts both.

## Per-wiki operations (cwd = wiki dir)

```bash
llm-wiki-base wiki ingest raw/inbox/foo.md    # index 1 source into search DB (writes no pages)
llm-wiki-base wiki reindex                    # incremental by content-hash (+ chunks_fts)
llm-wiki-base wiki reindex --check            # dry-run: what would index/drop + config drift + chunk index state
llm-wiki-base wiki reindex --full             # full rebuild (after embed_model/chunk_tokens/vector/fusion changes)
llm-wiki-base check lint                       # deterministic health-check (orphans, broken links, frontmatter, …)
llm-wiki-base check lint --fix                 # delete dangling rows + add missing index entries (additive)
llm-wiki-base check eval                       # P@k / R@k / MRR on golden queries (read-only)
llm-wiki-base check eval --compare             # tier1-weighted / rrf-text / rrf+vector + vector verdict
llm-wiki-base check eval --init                # create eval/golden.toml from template
llm-wiki-base review list             # pending proposals + diff size
llm-wiki-base review show <name>      # metadata + unified diff vs current page
llm-wiki-base review apply <name> [--by <human-id>]   # write page + log + reindex + delete proposal
llm-wiki-base review discard <name> --force
llm-wiki-base review new -t wiki/x/y.md -f body.md    # create a proposal from CLI
llm-wiki-base config show                # effective config, each key marked [default]/[toml]/[env …]
llm-wiki-base check verify wiki/<d>/concept/x.md --by <human-id>
llm-wiki-base check verify <path> --unverify
llm-wiki-base watch                      # daemon: inbox → ingest → reindex → lint (+ review-due nudges)
llm-wiki-base setup doctor                     # environment check + CLI ↔ AI-tool boundary
```

**`llm-wiki-base setup doctor`** checks: base runtime exists; `tools/` in base matches the
package file-by-file (prompts `llm-wiki-base base install` on drift); base-venv deps
(`mcp`, `fastembed`, and `tomli` only on venv < 3.11); registry (ghost path →
FAIL, wiki missing `id` → WARN); current wiki (has `.llm-wiki-base.toml`, has
`[wiki].profile`, registered or not, stale proposals); finally a table of the
**6 jobs that require an AI tool**. FAIL → exit 1, WARN → still 0.

## Upgrade / status

```bash
llm-wiki-base status                 # core local/latest tags + VERSION per wiki
llm-wiki-base upgrade --dry-run      # preview only
llm-wiki-base upgrade --to latest [--wiki <name>]
llm-wiki-base upgrade --to v0.2.0 --wiki my-wiki
```

Details: [upgrading.md](upgrading.md).

## Uninstall

```bash
llm-wiki-base uninstall --dry-run     # preview everything that would be removed
llm-wiki-base uninstall               # preview → confirm → remove
llm-wiki-base uninstall --yes         # no prompt (scripts/CI)
llm-wiki-base uninstall --keep-base   # drop configs only, keep ~/.llm-wiki-base runtime
llm-wiki-base uninstall --path /some/wiki   # also clean a wiki made with --no-register
llm-wiki-base uninstall --no-user-config     # leave ~/.claude, ~/.commandcode, … alone
```

Removes the **tool's footprint** across the machine:

- the global runtime dir `~/.llm-wiki-base/` (`tools/ rag/ scripts/ .venv/
  registry.toml`) — read for the wiki list *before* it is deleted;
- the `llm-wiki-base-mcp` server entry from every wiki/project MCP config
  (`.mcp.json`, `opencode.jsonc`, …) — other servers are kept, and a config file
  that becomes empty is deleted;
- every `llm-wiki-base-*` skill and its client links (`.claude/skills/`,
  `.opencode/commands/`) + the skills manifest;
- the marked research block `init project` wrote into the repo-root
  `AGENTS.md` / `.claude/CLAUDE.md` (surrounding text is preserved);
- each wiki's `.llm-wiki-base/` state dir (VERSION + tool backups).

**Wiki data is never touched** — `raw/`, `wiki/`, `rag/`, `eval/`, your
`.llm-wiki-base.toml`, `AGENTS.md`, and any skill you wrote yourself all survive.
Skills and MCP entries are matched by their own markers (command shape, name
prefix, manifest), not by guessing, so an unrelated server or skill that merely
shares a name is left in place.

The command cannot remove the Python package while it is running, so it prints
the exact follow-up line (`uv tool uninstall llm-wiki-base` or
`python -m pip uninstall llm-wiki-base`). It is idempotent — re-run to clean
anything added later.

## Translation

```bash
llm-wiki-base translate enable --lang vi --lang ja   # written to .llm-wiki-base.toml (comments kept)
llm-wiki-base translate status                       # show state
llm-wiki-base translate disable                      # off, langs kept
llm-wiki-base translate check --lang vi              # verify frontmatter + heading sync
```

Details: [translation.md](translation.md).

## Config (`.llm-wiki-base.toml`)

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
k = 8                     # cutoff for `llm-wiki-base check eval`

[review]
interval_days = 7         # review skill only runs full past this mark
max_pages = 80

[lifecycle]
default_stale_after_days = 180

[lint]
banned_terms = []
```

Changing `embed_model` / `chunk_tokens` / `vector` / `fusion` → run
`llm-wiki-base wiki reindex --full`. Runtime plumbing (paths) still goes through `.env` +
env vars.

`chunk_tokens` and `rrf_k` are **measured no-ops** on small wikis: 256/512/1024
give identical chunk counts when every section is short, and an `rrf_k` sweep of
20→250 produced identical numbers. Don't touch them until your own wiki's eval
says otherwise.

`llm-wiki-base setup` never overwrites an existing `.llm-wiki-base.toml` (only patches a
missing `[wiki]`), and every command writing this file (`translate enable`,
`setup` profile) **preserves comments** — comments here are documentation, not
decoration.

Env overrides: `WIKI_EMBED_MODEL`, `WIKI_FUSION`, `WIKI_CHUNK_BM25`,
`WIKI_BM25_WEIGHT`, `WIKI_VEC_WEIGHT` (last two only apply when
`fusion = "weighted"`). The installer does **not** pin retrieval env into the
MCP entry — pinning there would disable `.llm-wiki-base.toml` inside MCP only
(env > TOML) while the CLI still reads it, i.e. the same wiki returning two
different results.
