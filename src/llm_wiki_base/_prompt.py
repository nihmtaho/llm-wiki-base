"""Interactive prompts for the CLI — arrow-key menus when there is a TTY.

`questionary` renders real select / checkbox widgets, but it needs a terminal:
`CliRunner(input=...)` in tests, CI, and any piped invocation have no TTY. So
every question goes through this façade instead of calling questionary from
`cli.py`:

    TTY + questionary installed  → arrow-key menu
    otherwise                    → the same `rich.prompt` question it always was

The fallback is not a silent downgrade: it produces the identical prompts and
answer formats the wizard had before this module existed, so `--yes`, pipes and
CI keep working, and `--debug` prints why the rich widget did not appear.

`questionary` is imported lazily inside `_questionary()` so a machine without
it (or the base venv, which must not import the package) still runs the CLI.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from typing import Any

from llm_wiki_base import _ui
from llm_wiki_base._ui import console

#: A choice is either a bare value or a (value, display-label) pair.
Choice = str | tuple[str, str]

_q: Any = None
_q_resolved = False

_DEFAULT_STYLE = {
    "question": "bold",
    "answered": "green",
    "qmark": "cyan",
    "instruction": "dim",
    "pointer": "cyan",
    "highlighted": "cyan",
}


def _questionary() -> Any | None:
    """The questionary module, or None when it is not installed."""
    global _q, _q_resolved
    if not _q_resolved:
        _q_resolved = True
        try:
            import questionary
            _q = questionary
        except ImportError:
            _q = None
    return _q


def is_interactive() -> bool:
    """Can we render an arrow-key menu right now?"""
    if os.environ.get("LLM_WIKI_BASE_NO_MENU"):
        return False
    if _questionary() is None:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, OSError, ValueError):
        return False


def _why_not_interactive() -> str:
    if os.environ.get("LLM_WIKI_BASE_NO_MENU"):
        return "LLM_WIKI_BASE_NO_MENU is set"
    if _questionary() is None:
        return "questionary is not installed"
    return "stdin/stdout is not a TTY (piped input, CI, or --yes)"


def _plain(question: str) -> str:
    """Strip rich markup for questionary, which would print `[red]…` literally."""
    from rich.text import Text
    try:
        return Text.from_markup(question).plain
    except Exception:                       # unbalanced tags: show as typed
        return question


def _menu(question: str, typed: str) -> None:
    """One dim line explaining the fallback — only under --debug.

    Kept off stdout otherwise so it cannot pollute the panels every command
    already prints (nor the assertions in the wizard tests).
    """
    if _ui.is_debug():
        console.print(f"[dim]  (menu '{question}' → {typed}: {_why_not_interactive()})[/dim]")


def _normalize(choices: Sequence[Choice]) -> list[tuple[str, str]]:
    """[(value, label)] preserving order; label falls back to the value."""
    out: list[tuple[str, str]] = []
    for c in choices:
        if isinstance(c, tuple):
            out.append((c[0], c[1]))
        else:
            out.append((c, c))
    return out


def _style() -> Any | None:
    q = _questionary()
    if q is None:
        return None
    if _ui.is_no_color():
        return q.Style.from_dict({})          # --no-color promises zero escapes
    return q.Style.from_dict(_DEFAULT_STYLE)


def _backend() -> Any:
    """The questionary module, for callers that already passed `is_interactive()`."""
    q = _questionary()
    if q is None:                        # pragma: no cover - is_interactive() guards it
        raise RuntimeError("questionary is not installed")
    return q


def _ask(builder: Any) -> Any:
    """Run a questionary builder; None (Ctrl-C / EOF) aborts the command."""
    import typer
    answer = builder().ask()
    if answer is None:
        console.print("[dim]cancelled[/dim]")
        raise typer.Exit(0)
    return answer


def select(question: str, choices: Sequence[Choice], default: str = "") -> str:
    """One value out of a short list. Typed fallback = rich's `choices=` prompt."""
    pairs = _normalize(choices)
    values = [v for v, _ in pairs]
    if default and default not in values:
        values.insert(0, default)
        pairs.insert(0, (default, default))
    if is_interactive():
        q = _backend()
        labels = [q.Choice(title=lbl, value=val, checked=(val == default))
                  for val, lbl in pairs]
        return _ask(lambda: q.select(_plain(question), choices=labels, style=_style()))
    from rich.prompt import Prompt
    _menu(question, "typed name")
    return Prompt.ask(question, choices=values, default=default or values[0])


def checkbox(question: str, choices: Sequence[Choice],
             checked: Sequence[str] = (), hint: str = "") -> list[str]:
    """Any number of values (empty allowed). Typed fallback = comma-separated."""
    pairs = _normalize(choices)
    pre = [c for c in checked]
    if is_interactive():
        q = _backend()
        labels = [q.Choice(title=lbl, value=val, checked=(val in pre))
                  for val, lbl in pairs]
        builder = lambda: q.checkbox(_plain(question), choices=labels, style=_style())  # noqa: E731
        answer = _ask(builder)
        return [str(a) for a in answer]
    from rich.prompt import Prompt
    default = ",".join(pre)
    # The arrow-key menu shows why each row is or isn't pre-checked; a piped
    # prompt would hide all of that, so print the same list first. No square
    # brackets in the question: rich reads them as markup and eats the text.
    if len(pairs) > 1:
        _print_numbered(pairs, pre)
    if default:
        prompt = f"{question} — numbers or names, comma-separated, Enter keeps {default}"
    else:
        prompt = f"{question} — numbers or names, comma-separated, '-' for none"
    if hint:
        prompt = f"{prompt}  ·  {hint}"
    _menu(question, "comma-separated")
    return _resolve(pairs, split_csv(Prompt.ask(prompt, default=default or "-")))


def _print_numbered(pairs: list[tuple[str, str]], pre: list[str]) -> None:
    from rich.markup import escape
    for i, (value, label) in enumerate(pairs, 1):
        mark = "✓" if value in pre else " "
        console.print(f"  {mark} {i}. {escape(label)}")


def _resolve(pairs: list[tuple[str, str]], answers: list[str]) -> list[str]:
    """Accept `1,3` as well as `claude,zed`; anything else passes through untouched."""
    out: list[str] = []
    for token in answers:
        if token.isdigit() and 1 <= int(token) <= len(pairs):
            out.append(pairs[int(token) - 1][0])
        else:
            out.append(token)
    return out


def text(question: str, default: str = "") -> str:
    """A free-form string (name, path, language). Blank line answers `default`."""
    if is_interactive():
        q = _backend()
        return _ask(lambda: q.text(_plain(question), default=default, style=_style()))
    from rich.prompt import Prompt
    _menu(question, "typed input")
    # rich returns `default` only for a truly empty answer, so `default=""` is
    # passed through rather than collapsed to None (None would come back as None).
    return Prompt.ask(question, default=default)


def confirm(question: str, default: bool = True) -> bool:
    """Yes/no gate before anything is written."""
    if is_interactive():
        q = _backend()
        return bool(_ask(lambda: q.confirm(_plain(question), default=default,
                                           style=_style())))
    from rich.prompt import Confirm
    _menu(question, "y/n")
    return bool(Confirm.ask(question, default=default))


def split_csv(raw: str) -> list[str]:
    """`'a, b ,c'` → `['a', 'b', 'c']`; a lone `-` means "nothing selected"."""
    items = [c.strip() for c in raw.split(",") if c.strip()]
    return [] if items == ["-"] else items
