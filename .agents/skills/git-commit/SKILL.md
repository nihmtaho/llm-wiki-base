---
# Claude Code (skill)
name: git-commit
description: 'Create git commits following the mandatory commit-message + git-flow rule — conventional-commit format `(type(scope): subject)`, no Co-Authored-By/AI-attribution trailer, never commit directly on main. Use whenever the user asks to commit changes, says "commit this", "git commit", "commit and push", "merge", wants a PR prepared, or any time you (the agent) are about to run `git commit` yourself. A pre-commit guard runs the bundled validator automatically on every `git commit` Bash call and will block a non-compliant one — this skill is how you get it right the first time and report it back cleanly.'
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

Skill operationalizes the conventional-commit rule. Source of truth is the project's commit-message + git-flow rule; this skill wins on conflict.

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

## Output format — always this exact shape, every run

End every run with this block (fill values, keep format identical):

```
## Git commit
- Branch          : <branch> (created new: yes|no)
- Message         : <type>(<scope>): <subject>
- Files committed : <path1>, <path2>, ...
- Validator       : PASS|FAIL (<reason if FAIL>)
- Commit          : <short-sha>
- Follow-up       : none | <e.g. push, open PR, unrelated changes left unstaged>
```