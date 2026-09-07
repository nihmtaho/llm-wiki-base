# CLI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `llm-wiki-base` CLI as a goal-grouped tree with shared panel output and a 3-question wizard, keeping every old path working as a hidden alias.

**Architecture:** New typer groups (`setup`, `check`, `review`, extended `wiki`/`config`) own the handlers; one `aliases.py` dict registers hidden old paths that delegate to the same functions; `_ui.py` gains the only three renderers any command may use; global `--quiet/--no-color/--debug` flow through a single UI state object.

**Tech Stack:** Python ≥3.10, typer ≥0.12, rich ≥13, pytest (new dev dependency), typer `CliRunner` for tests.

---

## Repo map (read before starting)

- `src/llm_wiki_base/cli.py` (~969 lines) — the whole CLI: `app` + 6 sub-typer-apps
  (`init`, `wiki`, `base`, `translate`, `config`, `proposals`) + top-level commands
  (`ingest`, `reindex`, `lint`, `eval`, `watch`, `serve`, `verify`, `doctor`).
- `src/llm_wiki_base/_ui.py` — current renderers: `ok/fail/warn/skip/error`,
  `banner`, `section`, `done_panel`, `wiki_table`, `config_table`, `skill_table`;
  module-level `console = Console()`.
- `src/llm_wiki_base/init_personal.py` / `init_project.py` — `run(...)` worker functions
  the wizard calls (do NOT change their signatures; the wizard builds their args).
- `src/llm_wiki_base/installer.py` — `install_base()`, MCP entry builders (untouched).
- `src/llm_wiki_base/registry.py` — `list_wikis/add_wiki/remove_wiki/find` (untouched).
- Env var `LLM_WIKI_BASE_DIR` overrides the base dir; `HOME` override isolates
  user paths. Tests use both (see Task 1).
- Run the CLI in dev: `python -m llm_wiki_base ...` from repo root after
  `pip install -e ".[dev]"`.

## Scope check

Single subsystem (CLI surface only). Spec sections map to tasks:
§3 tree → Task 4; §4 output → Tasks 2–3; §5 wizard → Task 7; §6 help → Task 6;
§7 aliases → Task 5; §8 errors → Task 8; §9 tests → Tasks 1 + every task's steps;
§10 rollout → Task 9. No gaps.

## File structure (locked)

| File | Responsibility |
|------|---------------|
| `src/llm_wiki_base/_ui.py` (modify) | Only renderers: `ok_panel`, `err_panel`, `table`, UI state (`quiet`, `no_color`, `debug`); keep existing helpers until no caller uses them, then delete |
| `src/llm_wiki_base/cli.py` (modify) | New groups, moved handlers, global flags, hidden-alias registration, top-level exception guard |
| `src/llm_wiki_base/aliases.py` (create) | Single `OLD_TO_NEW: dict[tuple[str, ...], tuple[str, ...]]` mapping, e.g. `("init", "personal") → ("setup", "personal")` |
| `tests/conftest.py` (create) | `CliRunner` fixture, isolated env (`LLM_WIKI_BASE_DIR` + `HOME` → tmp) |
| `tests/test_*.py` (create) | One file per task below; never put two tasks' tests in one file |

---

### Task 1: Test harness

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py` (empty), `tests/conftest.py`
- Test: `tests/conftest.py` itself (smoke test below proves isolation)

- [ ] **Step 1: Add pytest as a dev extra**

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]
```

Append after the `[project.scripts]` block in `pyproject.toml`.

- [ ] **Step 2: Install and create the test layout**

Run: `pip install -e ".[dev]" && mkdir -p tests && touch tests/__init__.py`
Expected: install succeeds, `python -m pytest --version` prints 8.x.

- [ ] **Step 3: Write conftest with isolated env**

```python
import os
import pytest
from typer.testing import CliRunner


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    """Point base dir + HOME at tmp so tests never touch real state."""
    base = tmp_path / "base"
    home = tmp_path / "home"
    base.mkdir()
    home.mkdir()
    monkeypatch.setenv("LLM_WIKI_BASE_DIR", str(base))
    monkeypatch.setenv("HOME", str(home))
    return {"base": base, "home": home}
```

- [ ] **Step 4: Prove isolation with a smoke test**

Create `tests/test_harness.py`:

```python
import os


def test_env_is_isolated(isolated_env):
    assert os.environ["LLM_WIKI_BASE_DIR"] == str(isolated_env["base"])
    assert os.environ["HOME"] == str(isolated_env["home"])
```

Run: `python -m pytest tests/test_harness.py -q`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/
git commit -m "test(cli): harness with isolated env and CliRunner fixtures"
```

---

### Task 2: Shared output renderers (`_ui` v2)

**Files:**
- Modify: `src/llm_wiki_base/_ui.py`
- Test: `tests/test_ui.py`

Spec §4: every command renders through `ok_panel` / `err_panel` / `table`.
UI state lives in one place so global flags (Task 3) can flip it.

- [ ] **Step 1: Write the failing test**

```python
from llm_wiki_base import _ui


def test_ok_panel_quiet_prints_facts_only(capsys):
    _ui.set_quiet(True)
    try:
        _ui.ok_panel("Wiki ready", ["name: demo"], ["llm-wiki-base wiki add demo"])
    finally:
        _ui.set_quiet(False)
    out = capsys.readouterr().out
    assert "name: demo" in out
    assert "Wiki ready" not in out
    assert "╭" not in out and "╮" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ui.py -q`
Expected: FAIL with `has no attribute 'set_quiet'` (or `ok_panel`).

- [ ] **Step 3: Write minimal implementation**

Append to `src/llm_wiki_base/_ui.py`:

```python
_state = {"quiet": False, "no_color": False, "debug": False}


def set_quiet(value: bool) -> None:
    _state["quiet"] = value


def set_no_color(value: bool) -> None:
    global console
    _state["no_color"] = value
    console = Console(no_color=value)


def set_debug(value: bool) -> None:
    _state["debug"] = value


def is_debug() -> bool:
    return _state["debug"]


def ok_panel(title: str, facts: list[str], next_steps: list[str] | None = None) -> None:
    """Success panel. Quiet mode prints facts only, no panel, no next steps."""
    if _state["quiet"]:
        for line in facts:
            console.print(line)
        return
    body = "\n".join(facts)
    if next_steps:
        numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(next_steps))
        body += f"\n[dim]Next:[/dim]\n{numbered}"
    console.print(Panel(
        body,
        title=f"[bold green]\u2713 {title}[/bold green]",
        border_style="green",
        padding=(0, 2),
    ))


def err_panel(what: str, fix: str = "") -> None:
    """Error panel. Quiet mode prints `Error: <what>` plus fix on one line each."""
    if _state["quiet"]:
        console.print(f"Error: {what}")
        if fix:
            console.print(f"Fix: {fix}")
        return
    body = what
    if fix:
        body += f"\n[dim]Fix:[/dim] {fix}"
    console.print(Panel(
        body,
        title="[bold red]\u2717 Error[/bold red]",
        border_style="red",
        padding=(0, 2),
    ))


def table(title: str, headers: list[str], rows: list[list[str]]) -> None:
    """Generic listing table. Quiet mode prints one ` | `-joined line per row."""
    if _state["quiet"]:
        for row in rows:
            console.print(" | ".join(row))
        return
    t = Table(title=title or None, header_style="bold cyan", show_lines=False)
    for h in headers:
        t.add_column(h, overflow="fold")
    for row in rows:
        t.add_row(*row)
    console.print(t)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ui.py -q`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/_ui.py tests/test_ui.py
git commit -m "feat(cli): shared ok/err/table renderers with quiet mode"
```

---

### Task 3: Global flags `--quiet/--no-color/--debug`

**Files:**
- Modify: `src/llm_wiki_base/cli.py`
- Test: `tests/test_global_flags.py`

Flags must work on every command, so they live on an `@app.callback()`.
`ctx.obj` carries nothing; flags flip `_ui` state directly (set in Task 2).

- [ ] **Step 1: Write the failing test**

```python
from typer.testing import CliRunner
from llm_wiki_base.cli import app


def test_quiet_flag_suppresses_panels(runner: CliRunner, isolated_env):
    result = runner.invoke(app, ["--quiet", "wiki", "list"])
    assert result.exit_code == 0
    assert "╭" not in result.output and "╮" not in result.output


def test_no_color_flag_strips_ansi(runner: CliRunner, isolated_env):
    result = runner.invoke(app, ["--no-color", "wiki", "list"])
    assert result.exit_code == 0
    assert "\x1b[" not in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_global_flags.py -q`
Expected: FAIL — `wiki list` with empty registry prints a dim hint through the
module `console`, and `--quiet/--no-color` options do not exist yet
(typer exits 2, "No such option").

- [ ] **Step 3: Write minimal implementation**

Add an app callback near the top of `cli.py` (after the `app = typer.Typer(...)`
definition), and make the empty-registry hint respect quiet mode:

```python
@app.callback()
def _global_options(
    ctx: typer.Context,
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Facts only, no panels."),
    no_color: bool = typer.Option(False, "--no-color", help="Strip ANSI colors."),
    debug: bool = typer.Option(False, "--debug", help="Show full tracebacks on errors."),
) -> None:
    _ui.set_quiet(quiet)
    _ui.set_no_color(no_color)
    _ui.set_debug(debug)
```

In `wiki_list_cmd`, replace the empty-registry line with:

```python
    if not wikis:
        if _ui.is_quiet():
            return
        console.print("[dim]Registry rỗng. Chạy `llm-wiki-base setup` để tạo wiki đầu tiên.[/dim]")
        return
```

Add to `_ui.py`:

```python
def is_quiet() -> bool:
    return _state["quiet"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_global_flags.py tests/test_ui.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/cli.py src/llm_wiki_base/_ui.py tests/test_global_flags.py
git commit -m "feat(cli): global --quiet/--no-color/--debug flags"
```

---

### Task 4: New canonical tree

**Files:**
- Modify: `src/llm_wiki_base/cli.py`
- Test: `tests/test_tree.py`

Spec §3. New groups: `setup` (personal/project/tools/doctor), `check`
(lint/verify/eval); `wiki` gains `ingest`/`reindex`; `config` gains `path`;
`proposals` handlers move under new `review` group (old `proposals` path itself
is re-added as alias in Task 5). Handler bodies move verbatim — only the
decorator and function location change.

- [ ] **Step 1: Write the failing test**

```python
from typer.testing import CliRunner
from llm_wiki_base.cli import app


def test_canonical_groups_exist(runner: CliRunner):
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ["setup", "wiki", "check", "review", "translate", "config"]:
        assert group in result.output


def test_check_lint_reachable(runner: CliRunner, isolated_env):
    result = runner.invoke(app, ["check", "lint", "--help"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tree.py -q`
Expected: FAIL — `setup`, `check`, `review` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

In `cli.py`, following the existing `init_app` pattern:

```python
setup_app = typer.Typer(help="Set up wikis, tools and health checks")
app.add_typer(setup_app, name="setup")

check_app = typer.Typer(help="Check wiki health: lint, verify, eval")
app.add_typer(check_app, name="check")

review_app = typer.Typer(help="Review AI-proposed wiki edits (wiki/.proposals/)")
app.add_typer(review_app, name="review")
```

Then move each handler body verbatim under its new decorator:

- `@init_app.command("personal")` → `@setup_app.command("personal")`
  (function `init_personal_cmd` keeps its body; same for `"project"`)
- `@base_app.command("install")` → `@setup_app.command("tools")`
- `def doctor...` (top-level `@app.command("doctor")`) → `@setup_app.command("doctor")`
- top-level `lint`/`verify`/`eval` → `@check_app.command(...)` same names
- top-level `ingest`/`reindex` → `@wiki_app.command(...)` same names
- `@base_app.command("path")` → `@config_app.command("path")`
- `@proposals_app.command(...)` (list/show/apply/new/discard) →
  `@review_app.command(...)` same names; delete `proposals_app` registration
- top-level `init_interactive` wizard (the `@init_app.callback`) moves to
  `setup_app` callback in Task 7; leave it on `init_app` for now (Task 5 aliases it)

Keep `translate`, `config show`, `serve`, `watch` exactly where they are.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tree.py -q`
Expected: pass. Also run `python -m llm_wiki_base --help` manually and confirm the
six groups render.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/cli.py tests/test_tree.py
git commit -m "feat(cli): goal-grouped setup/check/review tree, wiki/config absorb orphans"
```

---

### Task 5: Hidden aliases for every old path

**Files:**
- Create: `src/llm_wiki_base/aliases.py`
- Modify: `src/llm_wiki_base/cli.py`
- Test: `tests/test_aliases.py`

Spec §7. One dict, hidden commands, identical behavior. Aliases delegate to the
new handler functions — import them, do not copy bodies.

- [ ] **Step 1: Write the failing test**

```python
from typer.testing import CliRunner
from llm_wiki_base.cli import app
from llm_wiki_base.aliases import OLD_TO_NEW

EXPECTED = [
    (("init", "personal"), ("setup", "personal")),
    (("init", "project"), ("setup", "project")),
    (("base", "install"), ("setup", "tools")),
    (("doctor",), ("setup", "doctor")),
    (("ingest",), ("wiki", "ingest")),
    (("reindex",), ("wiki", "reindex")),
    (("lint",), ("check", "lint")),
    (("verify",), ("check", "verify")),
    (("eval",), ("check", "eval")),
    (("proposals", "list"), ("review", "list")),
    (("proposals", "show"), ("review", "show")),
    (("proposals", "apply"), ("review", "apply")),
    (("proposals", "new"), ("review", "new")),
    (("proposals", "discard"), ("review", "discard")),
    (("base", "path"), ("config", "path")),
]


def test_alias_table_is_complete():
    assert set(OLD_TO_NEW.items()) == {(o, n) for o, n in EXPECTED}


def test_old_and_new_help_match(runner: CliRunner):
    for old, new in EXPECTED:
        old_help = runner.invoke(app, [*old, "--help"])
        new_help = runner.invoke(app, [*new, "--help"])
        assert old_help.exit_code == 0, old
        assert old_help.output == new_help.output, old


def test_aliases_hidden_from_help(runner: CliRunner):
    top = runner.invoke(app, ["--help"]).output
    assert "proposals" not in top
    assert "doctor" not in top.split("setup")[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_aliases.py -q`
Expected: FAIL — `llm_wiki_base.aliases` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `src/llm_wiki_base/aliases.py`:

```python
"""Old command paths, kept working as hidden aliases (spec §7).

Keys/values are path tuples. Registration lives in cli.py; this module is
the single source of truth so tests can assert completeness.
"""

OLD_TO_NEW: dict[tuple[str, ...], tuple[str, ...]] = {
    ("init", "personal"): ("setup", "personal"),
    ("init", "project"): ("setup", "project"),
    ("base", "install"): ("setup", "tools"),
    ("doctor",): ("setup", "doctor"),
    ("ingest",): ("wiki", "ingest"),
    ("reindex",): ("wiki", "reindex"),
    ("lint",): ("check", "lint"),
    ("verify",): ("check", "verify"),
    ("eval",): ("check", "eval"),
    ("proposals", "list"): ("review", "list"),
    ("proposals", "show"): ("review", "show"),
    ("proposals", "apply"): ("review", "apply"),
    ("proposals", "new"): ("review", "new"),
    ("proposals", "discard"): ("review", "discard"),
    ("base", "path"): ("config", "path"),
}
```

In `cli.py`, after all canonical registrations, add hidden delegating commands.
Pattern per alias (repeat for every row; single-word olds delegate directly):

```python
from llm_wiki_base.aliases import OLD_TO_NEW  # noqa: F401 (documents the contract)

@app.command("doctor", hidden=True)
def _alias_doctor(ctx: typer.Context) -> None:
    """Hidden alias for `setup doctor`."""
    from typer.main import get_command
    get_command(setup_app)(["doctor", *ctx.args[1:]] ... )
```

Simpler uniform pattern — call the new handler function directly. For commands
with no extra params this is one line; for ones with params, accept the same
signature and forward. Example for the group aliases:

```python
_alias_init_app = typer.Typer(hidden=True)
app.add_typer(_alias_init_app, name="init")

@_alias_init_app.command("personal", hidden=True)
def _alias_init_personal(ctx: typer.Context) -> None:
    """Hidden alias for `setup personal`. Accepts the same options."""
    ...
```

Concretely: each hidden command mirrors the new command's parameters and calls
the new function with them. E.g. if `setup personal` is
`def setup_personal_cmd(name: str = ..., ...)` then:

```python
@_alias_init_app.command("personal", hidden=True)
def _alias_init_personal(name: str = typer.Argument(None), ...) -> None:
    setup_personal_cmd(name=name, ...)
```

For zero-param commands (`lint`, `doctor`, ...): hidden command body is a single
call to the new handler. For `proposals *`: hidden `proposals` app whose five
commands forward to the five `review_*` functions with identical signatures.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_aliases.py -q`
Expected: pass. Manual spot check: `python -m llm_wiki_base doctor --help` output
equals `python -m llm_wiki_base setup doctor --help`, and root `--help` shows no
`proposals` group and no top-level `doctor`.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/aliases.py src/llm_wiki_base/cli.py tests/test_aliases.py
git commit -m "feat(cli): hidden aliases for all pre-redesign paths"
```

---

### Task 6: Help convention with examples

**Files:**
- Modify: `src/llm_wiki_base/cli.py`
- Test: `tests/test_help.py`

Spec §6: every command help has one line + `Examples` with 2–3 real commands.
Typer renders `\f`-separated epilogs; use that.

- [ ] **Step 1: Write the failing test**

```python
from typer.testing import CliRunner
from llm_wiki_base.cli import app
import typer


def _all_paths(command, prefix=()):
    paths = [prefix] if getattr(command, "callback", None) and prefix else []
    sub = getattr(command, "commands", None) or {}
    for name, sub_cmd in sub.items():
        paths += _all_paths(sub_cmd, (*prefix, name))
    return paths


def test_every_command_help_has_examples(runner: CliRunner):
    from typer.main import get_command
    root = get_command(app)
    missing = []
    for path in _all_paths(root):
        if not path:
            continue
        result = runner.invoke(app, [*path, "--help"])
        if result.exit_code != 0 or "Examples" not in result.output:
            missing.append(" ".join(path))
    assert not missing, f"help without Examples: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_help.py -q`
Expected: FAIL listing most commands (no `Examples` sections yet).

- [ ] **Step 3: Write minimal implementation**

Pattern per command — append an epilog after the docstring using `\f`
(typer passes text after `\f` through as rich epilog):

```python
@setup_app.command("personal")
def setup_personal_cmd(...) -> None:
    """Create a personal wiki in an empty folder.
    \f
    Examples:
        llm-wiki-base setup personal --name notes
        llm-wiki-base setup personal --name notes --clients claude,opencode
    """
```

Apply to every canonical command (aliases inherit the same function help
automatically since they share the handler — verify via the Task 5 test).
Also rewrite the six group `help=` strings and root help in goal order:
setup → wiki → check → review → translate → config → serve/watch. Typer lists
groups in registration order, so order the `add_typer` / command registrations
accordingly.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_help.py tests/test_aliases.py -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/cli.py tests/test_help.py
git commit -m "docs(cli): examples in every command help, goal-ordered groups"
```

---

### Task 7: Slim wizard with summary confirm

**Files:**
- Modify: `src/llm_wiki_base/cli.py` (wizard functions only)
- Test: `tests/test_wizard.py`

Spec §5. Current wizard asks 5–6 questions (type → name, lang, clients, mcp?,
skills?). Slim flow, max 3 + confirm:

1. Location — personal: `Tên wiki` (default = cwd name); project: `Project root`
   (default cwd) + `Wiki subdir` (default `project-wiki`). Counts as question 1
   (project root+subdir asked as one screen, two prompts — still one step).
2. Profile — auto-detected choice shown as default, user confirms
   (`personal` default in cwd; keep `Prompt.ask(choices=[...])`).
3. Clients — comma-separated, default `claude`, validated against
   `supported_clients()`.

Dropped questions become fixed defaults: `lang="en"`, skills `universal`,
MCP installed. Summary screen lists all resolved values, `Confirm.ask`
(default True) gates execution. `--yes` skips confirm; `--interactive` restores
the dropped questions (lang, skills target, skip_mcp) as extra prompts.

- [ ] **Step 1: Write the failing test**

```python
from typer.testing import CliRunner
from llm_wiki_base.cli import app


def test_setup_personal_yes_runs_with_defaults(runner: CliRunner, isolated_env, tmp_path):
    result = runner.invoke(
        app,
        ["setup", "personal", "--name", "demo", "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "home").exists()  # env actually isolated, sanity


def test_wizard_confirms_summary(runner: CliRunner, isolated_env):
    result = runner.invoke(app, ["setup"], input="personal\ndemo\nclaude\n\n")
    assert result.exit_code == 0, result.output
    assert "demo" in result.output  # summary screen echoed resolved values
```

Note: exact option names (`--name`, `--yes`) are defined in Step 3; if the
implementer names them differently, update the test to match — the behaviors
(pinned: non-interactive run, summary echo) are what matter.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_wizard.py -q`
Expected: FAIL — `setup personal` does not exist yet (Task 4 moves only the
non-interactive `personal`/`project` commands; the bare-`setup` callback and
`--yes` do not exist).

- [ ] **Step 3: Write minimal implementation**

Replace the moved `init_interactive` callback with a `setup_app` callback:

```python
@setup_app.callback(invoke_without_command=True)
def setup_interactive(ctx: typer.Context) -> None:
    """Slim wizard: location → profile → clients, then summary + confirm."""
    if ctx.invoked_subcommand is not None:
        return
    _ui.banner("llm-wiki-base setup", "Tạo wiki mới trong 3 câu hỏi.")
    wtype = Prompt.ask("Loại wiki", choices=["personal", "project"], default="personal")
    if wtype == "personal":
        _slim_personal(interactive=False)
    else:
        _slim_project(interactive=False)
```

`_slim_personal(interactive: bool)` asks name (default cwd name) and clients
(default `claude`, validated), fixes `lang="en"`, `skills_target="universal"`,
`skip_mcp=False`; prints a summary via `_ui.ok_panel("Ready to create", facts)`
where facts list every resolved value; `Confirm.ask("Tạo wiki?", default=True)`
gates `run_personal(...)`. With `interactive=True`, additionally prompt lang,
skills target and skip_mcp before the summary.

`setup personal` / `setup project` gain `--yes` (skip confirm) and
`--interactive` flags; non-interactive invocation with `--yes` never prompts.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_wizard.py -q`
Expected: pass. Manual check: `python -m llm_wiki_base setup` walks 3 questions +
summary in a scratch dir (use `LLM_WIKI_BASE_DIR=/tmp/...` to avoid real state).

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/cli.py tests/test_wizard.py
git commit -m "feat(cli): slim 3-question setup wizard with summary confirm"
```

---

### Task 8: Error pass — route everything through `err_panel`

**Files:**
- Modify: `src/llm_wiki_base/cli.py`, `src/llm_wiki_base/_ui.py` (only if a caller needs a new renderer arg — prefer not)
- Test: `tests/test_errors.py`

Spec §8: exit 0/1/2; user errors show `err_panel(what, fix)`; no tracebacks
unless `--debug`; unexpected exceptions become a friendly panel.

- [ ] **Step 1: Write the failing test**

```python
from typer.testing import CliRunner
from llm_wiki_base.cli import app


def test_missing_wiki_error_has_fix(runner: CliRunner, isolated_env):
    result = runner.invoke(app, ["wiki", "remove", "nope", "--force"])
    assert result.exit_code == 1
    assert "nope" in result.output
    assert "wiki list" in result.output  # the fix command
    assert "Traceback" not in result.output


def test_usage_error_exit_2(runner: CliRunner):
    result = runner.invoke(app, ["wiki", "add"])
    assert result.exit_code == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_errors.py -q`
Expected: FAIL — current `wiki_remove_cmd` prints a raw red line without the
fix in panel form (and other handlers print ad-hoc `console.print` errors).

- [ ] **Step 3: Write minimal implementation**

Two changes, applied handler by handler until the suite is green:

1. Replace every user-error `console.print(f"[red]Error:[/red] ...")` with:

```python
_ui.err_panel(f"wiki '{name}' không có trong registry", "llm-wiki-base wiki list")
raise typer.Exit(1)
```

2. Wrap dispatch in a top-level guard so unexpected exceptions never dump
tracebacks by default. At the end of `cli.py`:

```python
def main() -> None:
    try:
        app()
    except Exception as exc:  # noqa: BLE001 — last-resort guard, spec §8
        if _ui.is_debug():
            raise
        _ui.err_panel(f"Unexpected error: {exc}", "llm-wiki-base --debug <same command> for traceback")
        raise typer.Exit(1)
```

And point the entry point at it: `pyproject.toml`
`llm-wiki-base = "llm_wiki_base.cli:main"` (was `...cli:app`); `__main__.py` calls
`main()` if it currently calls `app()` — check and update.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/ -q`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/llm_wiki_base/cli.py src/llm_wiki_base/_ui.py pyproject.toml src/llm_wiki_base/__main__.py tests/test_errors.py
git commit -m "feat(cli): err_panel for user errors, guarded entrypoint"
```

---

### Task 9: Final verification and cleanup

**Files:**
- Modify: any leftover ad-hoc `console.print` in `cli.py`; delete now-unused
  `_ui` helpers (`ok/fail/warn/skip/error`, `banner`, `done_panel`,
  `wiki_table`, `config_table`, `skill_table`) only if zero callers remain
  (verify with `grep -rn "_ui\.\(ok\|fail\|warn\|skip\|error\|banner\|done_panel\|wiki_table\|config_table\|skill_table\)(" src/`)
- Test: full suite + manual smoke

- [ ] **Step 1: Delete dead renderers (if unused)**

Run the grep above. If a helper has callers, migrate that caller to
`ok_panel`/`err_panel`/`table` first, then delete the helper.

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: all green, no warnings about unknown marks.

- [ ] **Step 3: Manual smoke of the five critical flows**

```bash
export LLM_WIKI_BASE_DIR=/tmp/wikismoke
python -m llm_wiki_base --help
python -m llm_wiki_base setup --help
python -m llm_wiki_base doctor --help      # alias: must equal `setup doctor --help`
diff <(python -m llm_wiki_base doctor --help) <(python -m llm_wiki_base setup doctor --help) && echo ALIAS_OK
python -m llm_wiki_base --quiet wiki list; echo "exit=$?"
python -m llm_wiki_base wiki remove nope --force; echo "exit=$?"
rm -rf /tmp/wikismoke
```

Expected: groups in goal order; `ALIAS_OK`; quiet prints nothing on empty
registry with `exit=0`; remove-nonexistent prints panel + `exit=1`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(cli): drop dead renderers after redesign cutover"
```

Skip this commit if Step 1 deleted nothing (note it in the handoff instead).

---

## Self-review

1. **Spec coverage:** §3→Task 4 (+5 aliases); §4→Tasks 2–3; §5→Task 7;
   §6→Task 6; §7→Task 5; §8→Task 8; §9→Task 1 + per-task tests; §10→Task 9.
   No gaps.
2. **Placeholder scan:** no TBD/TODO; every code step shows real code with real
   symbol names (`setup_app`, `OLD_TO_NEW`, `ok_panel`, `run_personal`,
   `supported_clients`, `typer.Exit`, `CliRunner`). Task 5's per-alias forwarding
   is spelled as an explicit mirror-signature pattern with one worked example —
   the long tail is mechanical, not vague. Task 7 allows renaming `--name`/`--yes`
   with the test updated to match; behaviors pinned are the contract.
3. **Type consistency:** `_ui` state functions (`set_quiet`, `set_no_color`,
   `set_debug`, `is_quiet`, `is_debug`) are defined once in Task 2/3 and used
   identically later. `OLD_TO_NEW` tuple-keyed in both `aliases.py` and tests.
   `main()` entry point change is consistent across `pyproject.toml` +
   `__main__.py` in Task 8.
