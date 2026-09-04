---
# Claude Code (skill)
name: llm-wiki-release
description: 'Release llm-wiki-base (stable + beta) per SemVer + Conventional Commits + Keep a Changelog, using only git and gh CLI'
# Cursor (.mdc / rule)
alwaysApply: false
globs: ["pyproject.toml", "src/llm_wiki/__init__.py", "CHANGELOG.md"]
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
[SemVer 2.0.0](https://semver.org) + [Conventional Commits 1.0.0](https://www.conventionalcommits.org) + [Keep a Changelog 1.1.0](https://keepachangelog.com). Tag convention `vX.Y.Z` (matches `llm-wiki upgrade`).

## 0. Preconditions — check before anything else

```bash
git status --short          # must be empty (no junk commits, no env files)
git branch --show-current   # must be main
git fetch origin && git log --oneline origin/main -1 && git log --oneline -1
# both lines above must show the same commit (main synced, never release from a branch)
gh auth status              # must be logged in
python3 -m pytest tests/ -q # must be green
```

The version has TWO sources that must match: `pyproject.toml` (`version =`) and `src/llm_wiki/__init__.py` (`__version__ =`).

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
i = Path("src/llm_wiki/__init__.py"); s = i.read_text()
i.write_text(re.sub(r'^__version__ = ".*"$', f'__version__ = "{new}"', s, count=1, flags=re.M))
EOF
grep -n 'version =\|__version__' pyproject.toml src/llm_wiki/__init__.py
# both printed lines must show the same X.Y.Z before continuing
```

## 3. CHANGELOG.md (Keep a Changelog)

If the file does not exist yet, create the `## [Unreleased]` + `## [X.Y.Z] - YYYY-MM-DD` frame with `Added/Changed/Fixed` groups. Summarize from conventional commits, written for users (never paste raw log).

## 4. Commit the release

```bash
git add pyproject.toml src/llm_wiki/__init__.py CHANGELOG.md
git status --short   # only the 3 files above
git commit -m "chore(release): vX.Y.Z"
```

## 5. Tag (annotated, on main, after the commit)

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git show vX.Y.Z --stat | head -n 10   # verify the tag points at the release commit
```

## 6. Push (never --force main/tags)

```bash
git push origin main
git push origin vX.Y.Z
```

## 7. GitHub Release (gh CLI)

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "Summary from CHANGELOG:
- ...
- ..."
gh release view vX.Y.Z   # verify
```

## 7b. Beta release (prerelease, when pre-stable testing is needed)

SemVer prerelease numbering `X.Y.Z-beta.N` (`beta.1`, `beta.2`, ... for the same stable target; precedence is lower than stable so it never becomes `latest`).

```bash
NEW=X.Y.ZbN   # version files use PEP 440 form for pip safety (e.g. 0.2.0b1)
# bump both version files as in step 2, CHANGELOG gets a ## [X.Y.Z-beta.N] entry
git add pyproject.toml src/llm_wiki/__init__.py CHANGELOG.md
git commit -m "chore(release): vX.Y.Z-beta.N"
git tag -a vX.Y.Z-beta.N -m "vX.Y.Z-beta.N"
git push origin main && git push origin vX.Y.Z-beta.N
gh release create vX.Y.Z-beta.N --prerelease --title "vX.Y.Z-beta.N" --notes "Beta, please test:
- ...
- ..."
gh release view vX.Y.Z-beta.N   # verify, must show `Pre-release`
```

Notes:

- File versions (`X.Y.ZbN`) and tag/release (`vX.Y.Z-beta.N`) differ on purpose: pip only understands PEP 440, GitHub prerelease only SemVer-with-hyphen.
- `llm-wiki upgrade --to latest` skips betas by design (it only matches stable `vX.Y.Z`). To try a beta: `git checkout vX.Y.Z-beta.N` (+ reinstall unless editable) and verify manually; `--to <beta>` is currently unsupported.
- Going stable: continue the normal process (steps 2–7) with `X.Y.Z`, folding the beta CHANGELOG entry into the stable one. Never delete beta releases/tags after stable lands (keep the testing history).

## 8. Post-release

- `llm-wiki status` on another machine must show the new latest.
- Broken release: `gh release delete vX.Y.Z --yes && git push origin :vX.Y.Z && git tag -d vX.Y.Z`, fix, redo from step 2 with PATCH+1. Never move a tag anyone may use.

## Forbidden

- Tagging/committing a release from a feature branch. Rewriting pushed history (`rebase`/`push --force`/`amend` after push). Lightweight tags (missing `-a`, no message/date). Releasing on red tests or a dirty tree.
