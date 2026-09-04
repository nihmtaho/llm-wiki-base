---
# Claude Code (skill)
name: git-commit
description: 'Create git commits following the mandatory commit-message + git-flow rule — conventional-commit format `(type(scope): subject)`, no Co-Authored-By/AI-attribution trailer, never commit directly on main. Use whenever the user asks to commit changes, says "commit this", "git commit", "commit and push", "merge", wants a PR prepared, or any time you (the agent) are about to run `git commit` yourself. Also use for version releases (stable + beta): SemVer tags, changelog, annotated tag, push, gh release. A pre-commit guard runs the bundled validator automatically on every `git commit` Bash call and will block a non-compliant one — this skill is how you get it right the first time and report it back cleanly.'
# Cursor (.mdc / rule) — always-apply, no glob scoping
alwaysApply: true
# Windsurf
trigger: always_on
# Kiro
inclusion: always
# GitHub Copilot (.github/instructions/*.instructions.md)
applyTo: "**"
---
# Git Commit

Skill operationalizes the conventional-commit rule. Source of truth is this file; this skill wins on conflict.
Section 5 extends it to version releases (stable + beta).

## 0. Preconditions — check before staging anything

- **Branch**: `git rev-parse --abbrev-ref HEAD`. If `main`/`master`, branch first: `git checkout -b <type>/<short-description>` (e.g. `fix/column-diff-null-pk`). Never commit directly on main.
- **Scope of the diff**: `git status` + `git diff` (staged/unstaged). Stage only files for one logical change.
- **One logical change per commit** — split unrelated concerns, don't bundle.

## 1. Compose the message

Format: `type(scope): subject` (scope optional).

- `type` — one of `feat`/`fix`/`docs`/`style`/`refactor`/`perf`/`test`/`build`/`ci`/`chore`/`revert`.
- `subject` — imperative mood ("add" not "added"), lowercase after colon, no period, ≤72 chars.
- Breaking change: add `!` after type/scope (`feat(api)!: ...`), explain in body.
- Body (optional, blank line after subject) — *what*/*why*, not *how*.
- **Never add a `Co-Authored-By:` trailer or any other AI/tool attribution line.**

## 2. Validate before committing

Run bundled validator before committing — cheaper to fix now:

```
python .agents/skills/git-commit/scripts/check_git_commit.py -m "<message>"
```

(If `python` not on PATH, try `python3`.)

Fix report, re-run until `PASS`.

## 3. Commit

```
git add <files>          # only the files for this logical change
git commit -m "<subject>" [-m "<body>"]
```

A pre-commit guard runs the bundled validator on every `git commit` call and blocks messages that break the format/trailer rule or target `main`/`master`. Fix message/branch and retry. Guard can't see interactive editor (no `-m`/`-F`), so always pass `-m` explicitly.

## 4. Verify

`git log -1 --stat` — confirm commit message/files; `git status` clean.

## 5. Release a new version (stable + beta)

Same foundations, extended: [SemVer 2.0.0](https://semver.org) + [Keep a Changelog 1.1.0](https://keepachangelog.com). Tags `vX.Y.Z`. Only `git` + `gh`. Never release from a feature branch.

### 5.0 Preconditions (all must hold)

- `git status --short` empty; on `main`; `main == origin/main` after `git fetch origin`.
- `gh auth status` logged in; `python3 -m pytest tests/ -q` green.
- Version lives in TWO files that must match: `pyproject.toml` (`version =`) and `src/llm_wiki/__init__.py` (`__version__ =`).

### 5.1 Pick the version

- First release: `v0.1.0`. Then `git log <prev-tag>..HEAD --oneline`: `feat` → MINOR, `fix`/`perf` → PATCH, `!`/BREAKING → MAJOR.
- Beta: `X.Y.Z-beta.N` (`beta.1`, `beta.2`, … per target stable). Prerelease sorts below stable, never becomes `latest`.

### 5.2 Bump + changelog + commit

```bash
NEW=X.Y.Z   # beta: X.Y.ZbN (PEP 440, pip-safe — e.g. 0.2.0b1)
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
# both lines must show the new version before continuing
```

CHANGELOG.md (Keep a Changelog; create with an `[Unreleased]` frame if missing). Summarize conventional commits for humans, no raw log paste. Beta gets its own `## [X.Y.Z-beta.N]` section, merged into the stable section on stable release.

```bash
git add pyproject.toml src/llm_wiki/__init__.py CHANGELOG.md
git commit -m "chore(release): vX.Y.Z"   # beta: "chore(release): vX.Y.Z-beta.N"
```

(Sections 1–2 apply: the message must pass the bundled validator.)

### 5.3 Tag + push (never `--force` on main/tags)

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"   # beta: vX.Y.Z-beta.N
git show vX.Y.Z --stat | head -n 10   # verify tag points at the release commit
git push origin main
git push origin vX.Y.Z
```

### 5.4 GitHub Release

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "<CHANGELOG summary>"
gh release view vX.Y.Z   # verify
```

Beta adds `--prerelease` and notes must state what to test; verify it shows `Pre-release`.

### 5.5 Post-release rules

- `llm-wiki status` on another machine must show the new latest.
- File versions (`X.Y.ZbN`) vs tag/release (`vX.Y.Z-beta.N`) differ on purpose: pip only understands PEP 440, GitHub prerelease only SemVer-with-hyphen.
- `llm-wiki upgrade --to latest` ignores betas by design (stable-only tags). Try a beta via `git checkout vX.Y.Z-beta.N` (+ reinstall unless editable); explicit `--to <beta>` is unsupported.
- Broken release: `gh release delete vX.Y.Z --yes && git push origin :vX.Y.Z && git tag -d vX.Y.Z`, then redo from 5.2 with PATCH+1. Never move a used tag; keep beta tags after stable lands.

## Output format — always this exact shape, every run

End every run with this block (fill values, keep format identical):

```
## Git commit
- Branch          : <branch> (created new: yes|no)
- Message         : <type>(<scope>): <subject>
- Files committed : <path1>, <path2>, ...
- Validator       : PASS|FAIL (<reason if FAIL>)
- Commit          : <short-sha>
- Follow-up       : none | <e.g. push, open PR, unrelated changes left
```

Section 5 runs append a second block (same run, keep both):

```
## Git release
- Version         : vX.Y.Z (beta: vX.Y.Z-beta.N)
- Tag             : annotated, points at <short-sha>
- Pushed          : branch yes|no, tag yes|no
- GH release      : <url> (Pre-release yes|no)
- llm-wiki status : shows latest yes|no
```