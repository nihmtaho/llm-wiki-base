# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
Versioning follows [SemVer 2.0.0](https://semver.org/); tags are `vX.Y.Z`.

## [Unreleased]

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
