---
# Claude Code (skill)
name: llm-wiki-base-release
description: 'Release llm-wiki-base (stable + beta) per SemVer + Conventional Commits + Keep a Changelog, using only git and gh CLI'
# Cursor (.mdc / rule)
alwaysApply: false
globs: ["pyproject.toml", "src/llm_wiki_base/__init__.py", "CHANGELOG.md"]
# Windsurf
trigger: release
# Kiro
inclusion: fileMatch
fileMatchPattern: "CHANGELOG.md,pyproject.toml"
# GitHub Copilot (.github/instructions/*.instructions.md)
applyTo: "pyproject.toml,CHANGELOG.md"
---
# LLM Wiki Release

The global-standard release process for this repo, using only `git` + `gh`:
[SemVer 2.0.0](https://semver.org) + [Conventional Commits 1.0.0](https://www.conventionalcommits.org) + [Keep a Changelog 1.1.0](https://keepachangelog.com). Tag convention `vX.Y.Z` (matches `llm-wiki-base upgrade`).

## 0. Preconditions — check before anything else

```bash
git status --short          # must be empty (no junk commits, no env files)
git branch --show-current   # must be main
git fetch origin && git log --oneline origin/main -1 && git log --oneline -1
# both lines above must show the same commit (main synced, never release from a branch)
gh auth status              # must be logged in
python3 -m pytest tests/ -q # must be green
```

The version has TWO sources that must match: `pyproject.toml` (`version =`) and `src/llm_wiki_base/__init__.py` (`__version__ =`).

## 1. Pick the version number (SemVer)

- First time: `v0.1.0` (`0.x` = unstable API, `1.0.0` once the public API is stable).
- After that, read `git log <prev-tag>..HEAD --oneline`: `feat` → MINOR, `fix`/`perf` → PATCH, `!` or `BREAKING CHANGE` → MAJOR.
- Never guess: list the commits for the user if the change type is unclear.

## 2. Bump the version (both files, separate commit if needed)

```bash
NEW=X.Y.Z
python3 - "$NEW" <<'EOF'
import re, sys
from pathlib import Path
new = sys.argv[1]
p = Path("pyproject.toml"); s = p.read_text()
p.write_text(re.sub(r'^version = ".*"$', f'version = "{new}"', s, count=1, flags=re.M))
i = Path("src/llm_wiki_base/__init__.py"); s = i.read_text()
i.write_text(re.sub(r'^__version__ = ".*"$', f'__version__ = "{new}"', s, count=1, flags=re.M))
EOF
grep -n 'version =\|__version__' pyproject.toml src/llm_wiki_base/__init__.py
# both printed lines must show the same X.Y.Z before continuing
```

## 2b. Release templates — copy verbatim

Every release must read the same. Only the version, the date and the bullets change: never reorder a section, never rename a group heading, never invent your own heading, never paste raw commit subjects.

### T1 — CHANGELOG.md version entry

The new section goes directly under `## [Unreleased]` (latest version first); any `## [Unreleased]` bullets move into it and `[Unreleased]` is left empty. Groups are the six from [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), in this fixed order — delete the empty ones, never write "None.":

    ## [X.Y.Z] - YYYY-MM-DD

    <optional one-line lead, only when the whole release needs one (e.g. "First release.")>

    ### Added
    - ...

    ### Changed
    - ...

    ### Deprecated
    - ...

    ### Removed
    - ...

    ### Fixed
    - ...

    ### Security
    - ...

Rules:

- `YYYY-MM-DD` = the day the tag is pushed (ISO 8601, never a regional format).
- Group meanings: `Added` new feature · `Changed` altered existing behaviour · `Deprecated` soon to be removed · `Removed` gone · `Fixed` bug fixes · `Security` vulnerabilities. Breaking change = a bullet under `Changed`, starting with **BREAKING**.
- Bullets are user-facing: the command/file/flag in backticks first, then what the user gains or must do. One notable change per bullet, not one per commit.
- Bottom of the file keeps a link block, newest first — `[Unreleased]: https://github.com/nihmtaho/llm-wiki-base/compare/vX.Y.Z...HEAD` and one line per version `[X.Y.Z]: https://github.com/nihmtaho/llm-wiki-base/compare/vPREV...vX.Y.Z` (`PREV` = the version below it; the very first version compares to itself). Note: this repo's `CHANGELOG.md` has no link block yet (`0.1.0`–`0.1.2` are brackets-only, so they render as literal text) — backfill it on the next release.
- Yanked release (pulled for a serious bug/security issue): keep the entry, retitle it `## [X.Y.Z] - YYYY-MM-DD [YANKED]`. Never delete a version from the changelog.

### T2 — GitHub Release notes (stable)

Body = the T1 section verbatim (groups + bullets, without the `## [X.Y.Z]` heading), then the fixed footer. Title always equals the tag name.

```bash
gh release create vX.Y.Z --verify-tag --title "vX.Y.Z" --notes "$(cat <<'EOF'
<lead line from T1, or: Release X.Y.Z (YYYY-MM-DD)>

### Added
- ...

### Fixed
- ...

---
Full changelog: CHANGELOG.md
Upgrade: `llm-wiki-base upgrade --to latest` · Install: `uv tool install "git+https://github.com/nihmtaho/llm-wiki-base.git@vX.Y.Z"`
EOF
)"
```

### T3 — GitHub Release notes (beta)

Same shape as T2, plus `--prerelease`, and the fixed first line so a beta is unmistakable:

```bash
gh release create vX.Y.Z-beta.N --prerelease --verify-tag --title "vX.Y.Z-beta.N" --notes "$(cat <<'EOF'
Beta of X.Y.Z (prerelease N) — please test. `upgrade --to latest` skips it by design.

### Added
- ...

---
Try it: `uv tool install "git+https://github.com/nihmtaho/llm-wiki-base.git@vX.Y.Z-beta.N"` (or `git checkout vX.Y.Z-beta.N` + reinstall)
EOF
)"
```

### T4 — Exact strings

| artifact | stable | beta |
|---|---|---|
| release commit subject | `chore(release): vX.Y.Z` | `chore(release): vX.Y.Z-beta.N` |
| annotated tag name / message | `vX.Y.Z` / `vX.Y.Z` | `vX.Y.Z-beta.N` / `vX.Y.Z-beta.N` |
| release title | `vX.Y.Z` | `vX.Y.Z-beta.N` |
| version files (step 2) | `X.Y.Z` | PEP 440: `X.Y.ZbN` |

## 3. CHANGELOG.md (Keep a Changelog)

Write the new section with **T1** (§2b). If the file does not exist yet, create the `## [Unreleased]` + `## [X.Y.Z] - YYYY-MM-DD` frame with the six groups. Summarize from conventional commits, written for users (never paste raw log).

## 4. Commit the release

```bash
git add pyproject.toml src/llm_wiki_base/__init__.py CHANGELOG.md
git status --short   # only the 3 files above
git commit -m "chore(release): vX.Y.Z"   # exact subject per T4, nothing added to it
```

## 5. Tag (annotated, on main, after the commit)

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"   # name and message per T4
git show vX.Y.Z --stat | head -n 10   # verify the tag points at the release commit
```

## 6. Push (never --force main/tags)

```bash
git push origin main
git push origin vX.Y.Z
```

## 7. GitHub Release (gh CLI)

Run **T2** verbatim, then `gh release view vX.Y.Z` and compare it against the CHANGELOG section — same bullets, same order.

## 7b. Beta release (prerelease, when pre-stable testing is needed)

SemVer prerelease numbering `X.Y.Z-beta.N` (`beta.1`, `beta.2`, ... for the same stable target; precedence is lower than stable so it never becomes `latest`).

```bash
NEW=X.Y.ZbN   # version files use PEP 440 form for pip safety (e.g. 0.2.0b1)
# bump both version files as in step 2, CHANGELOG gets a T1 section for [X.Y.Z-beta.N]
git add pyproject.toml src/llm_wiki_base/__init__.py CHANGELOG.md
git commit -m "chore(release): vX.Y.Z-beta.N"   # exact subject per T4
git tag -a vX.Y.Z-beta.N -m "vX.Y.Z-beta.N"
git push origin main && git push origin vX.Y.Z-beta.N
```

Then run **T3** verbatim and `gh release view vX.Y.Z-beta.N` (must show `Pre-release`).

Notes:

- File versions (`X.Y.ZbN`) and tag/release (`vX.Y.Z-beta.N`) differ on purpose: pip only understands PEP 440, GitHub prerelease only SemVer-with-hyphen.
- `llm-wiki-base upgrade --to latest` skips betas by design (it only matches stable `vX.Y.Z`). To try a beta: `git checkout vX.Y.Z-beta.N` (+ reinstall unless editable) and verify manually; `--to <beta>` is currently unsupported.
- Going stable: continue the normal process (steps 2–7) with `X.Y.Z`, folding the beta CHANGELOG entry into the stable one. Never delete beta releases/tags after stable lands (keep the testing history).

## 8. Post-release

- `llm-wiki-base status` on another machine must show the new latest.
- Broken release: `gh release delete vX.Y.Z --yes && git push origin :vX.Y.Z && git tag -d vX.Y.Z`, fix, redo from step 2 with PATCH+1. Never move a tag anyone may use.

## Forbidden

- Tagging/committing a release from a feature branch. Rewriting pushed history (`rebase`/`push --force`/`amend` after push). Lightweight tags (missing `-a`, no message/date). Releasing on red tests or a dirty tree.
- Free-styling the output: new/renamed/reordered CHANGELOG groups, a CHANGELOG section and GitHub Release body that differ, commit/tag/title strings that deviate from T4. The templates in §2b are the format — a release nobody can diff against the previous one is a bug.
