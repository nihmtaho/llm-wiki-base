#!/usr/bin/env python3
"""Validate a git commit message + branch against .agents/rules/core-rules.md's
"Commit Message Convention & Git Flow" rule.

Two ways to run it:
  - Self-check before committing:
      python check_git_commit.py -m "<message>"
  - Claude Code PreToolUse hook (wired in .claude/settings.json):
      python check_git_commit.py --hook
    Reads the tool-call JSON from stdin and — only when the Bash command being
    run is a `git commit` invocation — denies it if the message or branch
    breaks the rule.

Pure stdlib, no third-party deps: keeps behavior identical on Windows and
macOS without needing extra packages installed.
"""
import argparse
import json
import re
import shlex
import subprocess
import sys

COMMIT_TYPES = {
    "feat", "fix", "docs", "style", "refactor", "perf",
    "test", "build", "ci", "chore", "revert",
}
HEADER_RE = re.compile(
    r"^(?P<type>[a-z]+)(\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<subject>.+)$"
)
PROTECTED_BRANCHES = {"main", "master"}
COMMIT_SEGMENT_RE = re.compile(r"(?:^|\s)git\s+commit(?:\s|$)")


def current_branch():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def validate_branch(branch):
    if branch in PROTECTED_BRANCHES:
        return [
            f"cannot commit directly on '{branch}' — branch first "
            f"(git checkout -b <type>/<short-description>), then commit"
        ]
    return []


def validate_message(message):
    """Return a list of rule violations; empty means the message is compliant."""
    if not message or not message.strip():
        return ["commit message is empty"]

    problems = []
    lines = message.splitlines()
    header = lines[0]

    match = HEADER_RE.match(header)
    if not match:
        problems.append(
            f"header must match 'type(scope): subject' (scope optional) — got: {header!r}"
        )
    else:
        if match.group("type") not in COMMIT_TYPES:
            problems.append(
                f"type {match.group('type')!r} is not one of "
                f"{'/'.join(sorted(COMMIT_TYPES))}"
            )
        subject = match.group("subject")
        if subject.endswith("."):
            problems.append("subject must not end with a trailing period")
        if subject[:1].isupper():
            problems.append("subject must be lowercase right after the colon")
        if match.group("breaking") and len(lines) < 2:
            problems.append("breaking change ('!') needs a body explaining the break")

    if len(header) > 72:
        problems.append(f"subject line is {len(header)} chars, must be ≤ 72")

    if re.search(r"co-authored-by", message, re.IGNORECASE):
        problems.append(
            "message must not contain a Co-Authored-By trailer (or any AI/tool attribution)"
        )

    return problems


def find_commit_segments(command):
    """Split a (possibly compound) bash command on shell operators and return
    only the segments that invoke `git commit` (not commit-tree/commit-graph)."""
    segments = re.split(r"&&|\|\||;|\|", command)
    return [s.strip() for s in segments if COMMIT_SEGMENT_RE.search(s)]


def extract_message(segment):
    """Best-effort extraction of the message(s) passed via -m/--message/-F to a
    `git commit` segment. Returns None if there's nothing to statically check
    (e.g. no -m/-F at all — git would open an editor, which a headless agent
    can't do anyway)."""
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        return None  # unbalanced quoting we can't safely parse — don't block on a guess

    messages = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ("-m", "--message"):
            i += 1
            if i < len(tokens):
                messages.append(tokens[i])
        elif token.startswith("--message="):
            messages.append(token.split("=", 1)[1])
        elif token in ("-F", "--file"):
            i += 1
            if i < len(tokens):
                try:
                    with open(tokens[i], encoding="utf-8") as f:
                        messages.append(f.read())
                except OSError:
                    pass
        i += 1

    return "\n\n".join(messages) if messages else None


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def run_hook():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return  # nothing we can act on — allow

    if payload.get("tool_name") != "Bash":
        return

    command = payload.get("tool_input", {}).get("command", "")
    segments = find_commit_segments(command)
    if not segments:
        return

    problems = validate_branch(current_branch())
    for segment in segments:
        message = extract_message(segment)
        if message is None:
            continue  # can't statically see the message (e.g. editor-based) — let it through
        problems += validate_message(message)

    if problems:
        deny(
            "This commit breaks .agents/rules/core-rules.md's commit convention:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\nFix the message/branch and retry."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Validate a git commit message + branch against the project's commit rule."
    )
    parser.add_argument("-m", "--message", help="commit message to validate")
    parser.add_argument(
        "--hook", action="store_true",
        help="run as a Claude Code PreToolUse hook (reads JSON from stdin)",
    )
    args = parser.parse_args()

    if args.hook:
        try:
            run_hook()
        except Exception as exc:  # never let the hook crash a commit — fail open, but say why
            print(f"git-commit hook error (allowing): {exc}", file=sys.stderr)
        return

    if not args.message:
        parser.error('provide -m "<message>" to validate, or --hook to run as a Claude Code hook')

    problems = validate_branch(current_branch()) + validate_message(args.message)
    if problems:
        print("FAIL")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
