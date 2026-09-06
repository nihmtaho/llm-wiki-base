# llm-wiki

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)](#install)

An LLM-maintained wiki — compile knowledge **once**, maintain it **forever**.
Union retrieval (BM25 page + BM25 chunk + vector, RRF fusion) with a measurable
eval harness, an MCP bridge for AI tools, and init for both personal wikis and
codebase wikis.

Local-first. Python + SQLite (FTS5 BM25) + on-device vectors (fastembed).
No external services, no data lock-in.

> **How it runs:** [`docs/wiki-flow.html`](docs/wiki-flow.html) — animated canvas
> diagram, switchable personal ↔ project, showing exactly what is deterministic,
> what needs an LLM, and where the human decides.

## Contents

- [Install](#install)
- [Quickstart](#quickstart)
- [How it works](#how-it-works)
- [Wiki flavors](#wiki-flavors)
- [CLI](#cli)
- [Skills](#skills)
- [Configuration](#configuration)
- [Retrieval & eval](#retrieval--eval)
- [Human authority](#human-authority)
- [MCP bridge](#mcp-bridge)
- [Upgrading](#upgrading)
- [Safety & limitations](#safety--limitations)
- [Contributing](#contributing)
- [License](#license)

## Install

Requirements: **Python 3.10+** (3.11+ needs no `tomli` backport).

```bash
# 1. Install the package
git clone <url> llm-wiki-base && cd llm-wiki-base
pip install -e .

# 2. Install the global runtime (once per machine)
llm-wiki base install
# → ~/.llm-wiki-base/{tools/,rag/,scripts/,.venv/,registry.toml}

# 3. Create a wiki
mkdir my-wiki && cd my-wiki && llm-wiki setup   # interactive wizard
```

### Making `llm-wiki` available globally

`pip install -e .` usually runs inside the repo venv, so the script lives at
`<repo>/.venv/bin/llm-wiki` (macOS/Linux) or `<repo>/.venv/Scripts/llm-wiki.exe`
(Windows) — **not on PATH**. Options:

```bash
# macOS / Linux — symlink (recommended)
sudo ln -s "$(pwd)/.venv/bin/llm-wiki" /usr/local/bin/llm-wiki

# macOS / Linux — PATH, no sudo
echo 'export PATH="'"$(pwd)"'/.venv/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

```powershell
# Windows — symlink (Admin CMD/PowerShell)
mklink C:\Windows\llm-wiki.exe "%CD%\.venv\Scripts\llm-wiki.exe"

# Windows — PATH, no Admin
[Environment]::SetEnvironmentVariable("Path", "$env:Path;$PWD\.venv\Scripts", "User")
```

Fallback on any OS — call through the venv: `./.venv/bin/llm-wiki base install`
(Windows: `.venv\Scripts\llm-wiki.exe`).

## Quickstart

```bash
mkdir demo && cd demo
llm-wiki setup personal -c commandcode --lang vi   # or -c claude / opencode / zed
echo "# Notes\n\nExpo Router SplitView uses \`unstable_splitView\`." > raw/inbox/note.md

# One rule — ingest INDEXES, it never writes pages:
llm-wiki wiki ingest raw/inbox/note.md   # (A) deterministic: file INTO search DB
# (B) writing wiki pages is the SKILL's job: open an AI tool, run skill `llm-wiki-ingest`

llm-wiki wiki reindex && llm-wiki check lint && llm-wiki setup doctor
```

`llm-wiki setup doctor` tells you which commands the CLI handles alone and which
require an AI tool. Full command reference: [`docs/cli.md`](docs/cli.md).

## How it works

A document's journey — 9 steps, 3 handoffs of "who is working":

1. **Sources land in staging.** You drop files, `scripts/extract_{url,pdf,youtube}.py`
   generate them, or another AI calls MCP `wiki_submit` — always into `raw/inbox/`.
   No shortcut writes straight into `wiki/`.
2. **Ingest = skill + LLM.** Reads the whole source, 3–5 takeaways, discusses with
   you, picks a domain, then writes `wiki/<domain>/{source,entity,concept}/*.md`
    with provenance. CLI `llm-wiki wiki ingest` does **not** do this — it only indexes.
3. **Catalog.** `index.md` + `log.md` are re-derivable so the agent writes them;
   every other assertion stays out. `verified` left blank.
4. **Derived index.** `llm-wiki wiki reindex` by content-hash → `pages_fts`,
   `chunks_fts`, and vector chunks (when `vector = true`).
5. **Question → candidate pool.** Skill calls MCP `wiki_search` with
   `top_k = 2 × top_n_final`.
6. **RRF.** Three independent ranking channels → fused by rank, never raw scores.
7. **LLM rerank** (skill, not an in-code model) → cut to `top_n_final`.
8. **Cited answer** + unverified/stale flags. Good synthesis gets filed back as a
   new page so the wiki compounds.
9. **Human gate.** To change/claim: `wiki_propose_edit` → `.proposals/` →
    `llm-wiki review apply --by <you>` → `verify`.

Two reverse flows keep the wiki from rotting: `llm-wiki watch` loops 1→4 on new
files; `llm-wiki check lint` (deterministic) then skill `llm-wiki-review` (semantic)
push gaps into `wiki/alerts/`.

**Two-layer architecture:**

- **Global runtime** `~/.llm-wiki-base/` — tools, rag, scripts, one venv. Shared by all wikis.
- **Per-wiki data** — each wiki is a folder of data only (`raw/`, `wiki/`,
  `rag/.rag_index/`, `.env`, `.llm-wiki.toml`). No code, no venv.

**Three authority tiers** (explains the rest of the design):

| tier | what | written by | deletable |
|---|---|---|---|
| `wiki/*.md` | source of truth, with provenance | skill + LLM, human reviews | no |
| `raw/` | cache of origins (URLs in `sources:` are the real provenance) | you drop / `wiki_submit` | **yes** |
| `.wiki.db`, `rag/.rag_index/` | derived indexes | `llm-wiki wiki reindex` | **yes**, rebuildable |

## Wiki flavors

| | Personal | Project (codebase) |
|---|---|---|
| **For** | personal knowledge wiki | wiki of a code repo |
| **Location** | in-place (cwd) | `<root>/<wiki-dir>/` subfolder |
| **`[wiki].profile`** | `personal` | `codebase` |
| **Skills** | `llm-wiki-{ingest,query,lint,reindex,review,consolidate,translate}` | same set **+ `llm-wiki-research` at repo root** |

Both flavors **share skill names** — they differ by `[wiki].profile`, not by skill
set. MCP is centralized (`llm-wiki-base-mcp`): one machine-wide server entry
reads `registry.toml` to find wikis. Setup guide: [`docs/init.md`](docs/init.md).

## CLI

```bash
llm-wiki setup personal --name "My Knowledge" --lang vi
llm-wiki setup project -c claude -c opencode
llm-wiki wiki list                                   # wikis in registry.toml
llm-wiki wiki ingest raw/inbox/foo.md                # index one source (writes no pages)
llm-wiki wiki reindex && llm-wiki check lint && llm-wiki setup doctor
llm-wiki check eval --compare                        # retrieval A/B with verdict
llm-wiki review apply <name> --by you
llm-wiki upgrade --dry-run                           # skills+configs → newest GitHub tag
llm-wiki translate enable --lang vi --lang ja
```

Full reference (init flags, per-wiki commands, proposals, translation, doctor):
[`docs/cli.md`](docs/cli.md).

## Skills

8 skills, **no personal/project name split** — mode comes from `[wiki].profile`.
Installed by `llm-wiki setup` in two scopes:

| Skill | Scope | Role |
|---|---|---|
| `llm-wiki-ingest` | wiki | raw → source/entity/concept pages + cross-links + index/log + reindex |
| `llm-wiki-query` | wiki | answer from **the wiki you're in**: retrieval → rerank → cite → file synthesis |
| `llm-wiki-lint` | wiki | **deterministic** health-check: orphans, broken links, frontmatter, index sync |
| `llm-wiki-reindex` | wiki | build/diagnose derived indexes: `--check`, `--full`, dead channels |
| `llm-wiki-review` | wiki | **semantic** health-check: contradictions, staleness, trust gaps → `wiki/alerts/` |
| `llm-wiki-consolidate` | wiki | merge scattered logs/notes → canonical concepts (additive, distill-verify) |
| `llm-wiki-translate` | wiki | translate pages into `[translate].langs` (AI tool's LLM) |
| `llm-wiki-research` | **codebase root** | research **across wikis** via centralized MCP |

`llm-wiki-research` lives at `<repo>/.agents/skills/` instead of inside a wiki:
it must see every wiki, while wiki-scoped skills mind one wiki each. Boundary
with `query`: *query* = the wiki you're standing in (may file synthesis),
*research* = many wikis (staging only).

Installed skills are **copies** — after upgrading the package, refresh each wiki
with `llm-wiki upgrade` (backup + overwrite, prunes shipped-away skills, keeps
yours). See [`docs/upgrading.md`](docs/upgrading.md).

## Configuration

Behavior config per wiki (`.llm-wiki.toml`, **committed**). Precedence:
**env > TOML > default.** Key groups: `[wiki]` (profile, lang), `[retrieval]`
(fusion, channels, budgets), `[retrieval.weights]`, `[models]` (skill-layer LLM
contract — Python never calls an LLM), `[eval]`, `[review]`, `[lifecycle]`,
`[lint]`, `[translate]`. Changing `embed_model` / `chunk_tokens` / `vector` /
`fusion` requires `llm-wiki wiki reindex --full`. Full annotated example:
[`docs/cli.md`](docs/cli.md) (config section).

## Retrieval & eval

Union retrieval + RRF over three independent channels (`bm25_page`,
`bm25_chunk`, `vector_chunk`), LLM rerank at the skill layer, silent-channel
alarms instead of silent degradation, and a golden-query eval harness
(`P@k / R@k / MRR`, `eval --compare` with a vector verdict). Measured findings
(RRF trade-offs, when vector earns its keep): [`docs/retrieval-eval.md`](docs/retrieval-eval.md).

## Human authority

- **Trust tiers.** Every page has `generated: {by, at}`; optional
  `verified: {by, at}`. AI never sets `verified` —
  `llm-wiki check verify <page> --by <human-id>`. Retrieval still serves unverified
  pages, but skills must flag them.
- **Proposals = the write gate.** AI reads freely; asserting facts requires a
  human signature: `proposals new/list/show/apply/discard`. MCP
  `wiki_propose_edit` writes the same format.
- **Pins.** Important hand edits go in `wiki/pins.yml` and survive regeneration;
  contradicted pins route to `wiki/alerts/`, never silent reverts.

## MCP bridge

MCP is a **bridge** for AI tools — not a channel for writing to the wiki
directly. Tools: `wiki_search`, `semantic_search`, `wiki_read`, `wiki_list`,
`list_raw_source`, `read_raw_source`, `wiki_submit` (into `raw/inbox/` only),
`wiki_propose_edit`, `wiki_lint`. Resources: `registry://wikis`,
`wiki://<name>/index`, `wiki://<name>/log`. Per-client setup table and entry
format: [`docs/mcp.md`](docs/mcp.md).

## Upgrading

```bash
llm-wiki status                 # core local/latest tags + VERSION per wiki
llm-wiki upgrade --dry-run      # preview: which files change, per wiki
llm-wiki upgrade --to latest    # backup → sync skills + agent configs → stamp VERSION
llm-wiki upgrade --to v0.2.0 --wiki my-wiki
```

Upgrades every wiki in `registry.toml` to a GitHub tag (`vX.Y.Z`); project wikis
also re-sync the `codebase` skill at the project root. Migration notes for old
layouts and flag details: [`docs/upgrading.md`](docs/upgrading.md).

## Safety & limitations

- **Raw is cache** (gitignored) — delete freely. URLs in `sources:` are the real provenance.
- **AI proposes, human decides.** Re-derivable writes (index, log) are automatic; factual assertions wait in `.proposals/` for `apply`.
- **Contradiction = tell the human**, never materialize as an edge or pick a side silently.
- **Provenance required.** Every claim has a `[[wiki page]]` in-body or a URL in `sources:`.
- **No writes outside the wiki.** Proposed/proposal paths are normalized and confined to the target wiki's `wiki/`.
- **Known limits:** eval covers one wiki (no cross-wiki metric yet — see
  [`docs/tier3-roadmap.md`](docs/tier3-roadmap.md)); `[models]` is a paper
  contract for the skill layer (no headless ingest yet); `pages.embedding` is
  written but only read by `fusion="weighted"` (RRF fuses ranks, not vectors).

## Contributing

```bash
pip install -e .[dev]              # CLI venv + pytest/ruff/mypy
llm-wiki base install           # sync src/llm_wiki/base_tools → ~/.llm-wiki-base/tools/
PYTHONPATH=src python -m pytest tests/ -q   # gate 1: tests
ruff check src tests                       # gate 2: lint
mypy src/llm_wiki/registry.py src/llm_wiki/cli.py  # gate 3: types
```
All three gates run in CI (`.github/workflows/ci.yml`) and must be green
before any commit/PR.

- Commits follow Conventional Commits (`type(scope): subject`, no AI trailers,
  never on `main`) — enforced by a pre-commit guard; see skill `git-commit`.
- Releases (stable + beta, SemVer tags, changelog, `gh release`) — see skill `llm-wiki-release`.
- Source layout: `src/llm_wiki/` (CLI + installer + registry),
  `src/llm_wiki/base_tools/` (runs in the base venv, **must not** import the
  package), `src/llm_wiki/base_rag/`, `src/llm_wiki/skills/{wiki,codebase}/`
  (init copy source), `src/llm_wiki/templates/`.
- ⚠️ `src/llm_wiki/config_file.py` and `src/llm_wiki/base_tools/config_file.py`
  must match key-for-key (the latter is the fallback when tools run in the base
  venv without the package). `llm-wiki setup doctor` diffs `tools/` against the
  package and reports drift.
- Detailed docs: agent schema
  ([`_schema.md`](src/llm_wiki/templates/agents/_schema.md)) · wiki runbook
  ([`AGENTS.md`](src/llm_wiki/templates/agents/AGENTS.md),
  [`CLAUDE.md`](src/llm_wiki/templates/agents/CLAUDE.md)) ·
  init guide ([`docs/init.md`](docs/init.md)) · roadmap
  ([`docs/tier3-roadmap.md`](docs/tier3-roadmap.md)) · session history
  ([`docs/session/`](docs/session/)) · credits ([`docs/credits.md`](docs/credits.md)).

## License

MIT — see [LICENSE](LICENSE) (or `pyproject.toml`).
