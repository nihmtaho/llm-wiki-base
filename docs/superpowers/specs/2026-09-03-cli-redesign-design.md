# CLI Redesign — Design Spec

Date: 2026-09-03 | Status: approved, pending implementation plan

## 1. Goal

Rebuild the `llm-wiki-base` CLI around user goals instead of implementation history:
find any command in seconds, read consistent output, finish setup in 3 questions.
Human-in-terminal is the primary consumer; agents/scripts stay supported via
`--quiet` / `--no-color`, not via a separate machine interface.

Non-goals: new wiki features, MCP protocol changes, config file format changes,
removing any existing command path.

## 2. Decisions (from brainstorming)

| # | Question | Decision |
|---|----------|----------|
| 1 | Scope | Full overhaul: structure + output + interactive UX |
| 2 | Old paths | Keep working as hidden aliases, no deprecation warnings |
| 3 | Consumer | Human in terminal first |
| 4 | Pains | Hard discovery, inconsistent output, wizard friction, weak help |
| 5 | Tree | Variant A (medium regroup, §3) |
| 6 | Output | Panel + next-steps style (§4) |
| 7 | Wizard | Slim, max 3 questions + summary confirm (§5) |
| 8 | Help/alias/errors/tests | Approved as specified (§6–§9) |

## 3. Command tree (new canonical paths)

```
setup personal | setup project | setup tools | setup doctor
wiki add | wiki list | wiki remove | wiki ingest | wiki reindex
check lint | check verify | check eval
review list | review show | review apply | review new | review discard
translate enable | translate disable | translate status | translate check
config show | config path
serve
watch
```

Alias table (old → new, all hidden, all functional):

| Old | New |
|-----|-----|
| `init personal`, `init project` | `setup personal`, `setup project` |
| `base install` | `setup tools` |
| `doctor` | `setup doctor` |
| `ingest`, `reindex` | `wiki ingest`, `wiki reindex` |
| `lint`, `verify`, `eval` | `check lint`, `check verify`, `check eval` |
| `proposals *` | `review *` |
| `base path` | `config path` |

Unchanged: `translate *`, `config show`, `serve`, `watch`.

## 4. Output system (`_ui` v2)

Every command renders through shared renderers, no ad-hoc prints:

- `ok_panel(title, facts, next_steps)` — success panel + numbered next actions.
- `err_panel(what, fix)` — what failed + exact command to fix it.
- `table(headers, rows)` — all listings.
- Global flags: `--quiet` (facts only, no panels), `--no-color`; honor `NO_COLOR`.
- Errors never print tracebacks; `--debug` re-enables them.

## 5. Wizard (`setup personal|project`)

Max 3 questions: location (default sensed from cwd) → profile (auto-detected,
user confirms) → MCP clients (multi-select, pre-checked to installed clients).
Ends with a summary screen + confirm. `--yes` skips the confirm,
`--interactive` forces every question including advanced ones.

## 6. Help convention

Every command: one-line summary + `Examples` section with 2–3 real commands.
Group helps describe subcommands by user goal. Root `--help` lists groups
in goal order (setup → wiki → check → review → translate → config → daemons).

## 7. Alias mechanism

Single `OLD_TO_NEW` dict in one module (`src/llm_wiki_base/aliases.py`).
Old paths register as hidden typer commands delegating to the new handlers.
Hidden from `--help`, no warnings, identical behavior and exit codes.

## 8. Errors and exit codes

- `0` success.
- `1` user error (bad input, missing wiki) with `err_panel` + fix command.
- `2` usage error (typer default).
- Unexpected exceptions: friendly panel by default, traceback only with `--debug`.

## 9. Testing

Typer `CliRunner` tests, no new framework:

- Alias coverage: every old path resolves and matches new-path output.
- Help snapshot: every command help contains an `Examples` section.
- Wizard: simulated input walks the 3-question flow + confirm + `--yes`.
- Flags: `--quiet` emits no panels, `--no-color` emits no ANSI codes.

## 10. Rollout

Single feature branch, single PR against `main`. Conventional commits per
logical unit (tree, output, wizard, help, aliases). No version bump in this
change; `serve --mcp` behavior untouched.
