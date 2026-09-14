# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer 2.0.0](https://semver.org/); tags are `vX.Y.Z`.

## [Unreleased]

## [0.1.4] - 2026-09-14

### Added

- `llm-wiki-base-contribute`: a new **global** skill (installed once per machine to
  `~/.agents/skills/` + `~/.claude/skills/`) that drafts schema-valid wiki pages and
  stages them through MCP — `wiki_submit` → `raw/inbox/` for new sources,
  `wiki_propose_edit` → `wiki/.proposals/` for finished pages. AI proposes, human
  decides; it never writes `wiki/` directly and never sets `verified`. Installed by
  `setup tools|personal|project` (opt out with `--no-contribute`), and offered as a
  question in the interactive `setup` wizard.

### Fixed

- `setup`/`init` no longer crash with `FileNotFoundError` at import time when the
  current working directory has been deleted; the `--root` default now falls back to
  `~` instead of calling `Path.cwd()` during module load.
- `upgrade --to latest` picked the peeled ref (`v0.1.3^{}`) instead of the tag half
  the time — `ls-remote` reports both for annotated tags and set ordering decided the
  winner. The peeled ref is now ignored, so the resolved tag (and the `VERSION`
  stamp) is always `vX.Y.Z`.
- `upgrade` now re-syncs the user-global skills (`~/.agents/skills/` +
  `~/.claude/skills/`), matching `init`; previously a newly shipped global skill
  never reached existing installs.

## [0.1.3] - 2026-09-14

### Added

- `llm-wiki-base version` (and the `--version` flag) prints the installed package
  version.
- `setup` now chooses clients with an interactive arrow-key menu and only checks the
  clients this machine can prove exist (binary on PATH, config dir, or the macOS app
  bundle), so it stops creating config for clients you don't have. Support grew from 4
  to 9 clients (adds pi, cursor, copilot, codex, hermes); `zed` now reads `.zed/settings.json`.

### Changed

- `setup` stays usable non-interactively: `--yes`, pipes, and CI behave as before, and
  piped users get a numbered list of clients they can answer by number.

## [0.1.2] - 2026-09-11

### Added

- `llm-wiki-base uninstall`: removes the tool's footprint from the machine — the
  global runtime dir (`~/.llm-wiki-base/`), the MCP server entry from every
  wiki/project config, and all `llm-wiki-base-*` skills + client links + the
  marked root research block. Ingested **wiki data** (`raw/`, `wiki/`, `rag/`) is
  never deleted. `--dry-run` previews, `--yes` skips the prompt, `--keep-base`
  and `--path`/`--no-user-config` narrow the scope; the command is idempotent and
  prints the follow-up line to remove the CLI package itself.

### Fixed

- `init` now writes `.llm-wiki-base.toml` at the wiki root. The bundled config
  template kept a stale filename, so `init` silently skipped writing the file
  and `doctor` warned that the wiki root had no config.

## [0.1.1] - 2026-09-07

### Changed

- Promoted beta `0.1.1b1` to stable `0.1.1`.

## [0.1.1-beta.1] - 2026-09-07

Beta for the `llm-wiki-base` rename. Please test.

### Changed

- Renamed everything to `llm-wiki-base` — console script, package and module
  (`llm_wiki_base`), skill names, `.llm-wiki-base.toml`, `.llm-wiki-base/`
  state dir, `LLM_WIKI_BASE_*` env vars. Re-run `setup` to refresh MCP
  entries; rename or re-init old `.llm-wiki.toml` files.
- CLI help and prompts are English throughout (code comments stay Vietnamese).
- One-line global install per OS (`uv tool install …` + `setup tools`); wheel
  builds fixed (dropped duplicate `force-include`, relative symlinks).

### Added

- `setup doctor` warns when `llm-wiki-base` is not on PATH.
- Quality gates: `ruff` + `mypy` config and GitHub Actions CI.

### Fixed

- `registry.toml` survives Windows paths, quotes, and unicode (`tomli-w`).
- `review apply` emits machine-readable `RESULT` JSON (legacy `APPLIED` kept).
- Reserved pages (`index.md`/`log.md`) excluded from all index channels.

## [0.1.0] - 2026-09-04

First release.

### Added

- Union retrieval (BM25 page + BM25 chunk + vector) with RRF fusion and a
  golden-query eval harness (`eval`, `eval --compare`).
- 8 profile-aware skills (`llm-wiki-*`) for personal and codebase wikis, in
  `wiki` and `codebase` scopes, plus per-client distribution
  (Claude Code, OpenCode, Command Code, Zed).
- Centralized MCP server (`llm-wiki-base-mcp`) with registry-backed multi-wiki
  tools (`wiki_search`, `wiki_submit`, `wiki_propose_edit`, …).
- Human authority flow: trust tiers, `verify`, proposals
  (`new/list/show/apply/discard`), `pins.yml`.
- Wiki registry with stable UUIDs, `wiki list/add/remove`.
- `llm-wiki upgrade --to <tag|latest>` (+ `status`, `--dry-run`): backup,
  re-sync skills and agent configs for every registered wiki (including the
  `codebase` skill at project roots), stamp `.llm-wiki/VERSION`.
- Bilingual wiki support via `llm-wiki-translate` (`translate enable/status/disable/check`).
- `reindex` (incremental/full/check), `lint`, `watch`, `doctor`, `config show`.
- Release process skill (`llm-wiki-release`): SemVer tags, changelog,
  annotated tags, `gh release` (stable + beta).
- English README (standard-readme layout), `LICENSE` (MIT), topic guides under
  `docs/` (`cli`, `retrieval-eval`, `mcp`, `upgrading`, `translation`),
  animated `docs/wiki-flow.html`.

[Unreleased]: https://github.com/nihmtaho/llm-wiki-base/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/nihmtaho/llm-wiki-base/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/nihmtaho/llm-wiki-base/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/nihmtaho/llm-wiki-base/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/nihmtaho/llm-wiki-base/compare/v0.1.1-beta.1...v0.1.1
[0.1.1-beta.1]: https://github.com/nihmtaho/llm-wiki-base/compare/v0.1.0...v0.1.1-beta.1
[0.1.0]: https://github.com/nihmtaho/llm-wiki-base/compare/v0.1.0...v0.1.0
