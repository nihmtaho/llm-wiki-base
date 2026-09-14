"""The prompt façade must answer the same questions with and without a TTY.

Everything here runs through the non-TTY branch (pytest has no terminal), which
is exactly the branch `--yes`, pipes and CI depend on.

Answers carry no trailing newline on purpose: rich only applies a default when
`input()` handed back a truly empty string, and real `input()` strips it.
"""
import pytest

from llm_wiki_base import _prompt


@pytest.fixture(autouse=True)
def _reset_facade_cache():
    yield
    _prompt._q = None
    _prompt._q_resolved = False


def _feed(monkeypatch, answers):
    """Stub `input()` with a finite script — extra questions raise StopIteration."""
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(it))
    return it


def test_no_menu_without_a_tty(monkeypatch):
    monkeypatch.delenv("LLM_WIKI_BASE_NO_MENU", raising=False)
    assert _prompt.is_interactive() is False


def test_env_var_forces_the_typed_path(monkeypatch):
    class Tty:
        def isatty(self):
            return True

    monkeypatch.setattr(_prompt.sys, "stdin", Tty())
    monkeypatch.setattr(_prompt.sys, "stdout", Tty())
    monkeypatch.delenv("LLM_WIKI_BASE_NO_MENU", raising=False)
    assert _prompt.is_interactive() is True           # questionary is installed
    monkeypatch.setenv("LLM_WIKI_BASE_NO_MENU", "1")
    assert _prompt.is_interactive() is False          # ... unless switched off


def test_missing_questionary_degrades_to_rich(monkeypatch):
    monkeypatch.setattr(_prompt, "_q", None)
    monkeypatch.setattr(_prompt, "_q_resolved", True)
    assert _prompt.is_interactive() is False
    assert "not installed" in _prompt._why_not_interactive()


def test_select_typed_fallback(monkeypatch):
    _feed(monkeypatch, ["project"])
    assert _prompt.select("Wiki type", ["personal", "project"], "personal") == "project"


def test_select_blank_line_takes_default(monkeypatch):
    _feed(monkeypatch, [""])
    assert _prompt.select("Wiki type", ["personal", "project"], "personal") == "personal"


def test_select_adds_a_default_that_is_not_in_the_list(monkeypatch):
    _feed(monkeypatch, [""])
    got = _prompt.select("Skills target", ["universal", "skip"], default="claude")
    assert got == "claude"


def test_text_keeps_default_on_blank_line(monkeypatch):
    _feed(monkeypatch, [""])
    assert _prompt.text("Wiki name", default="notes") == "notes"


def test_text_returns_str_when_there_is_no_default(monkeypatch):
    _feed(monkeypatch, [""])
    assert _prompt.text("Wiki language") == ""


def test_confirm_blank_line_takes_default(monkeypatch):
    _feed(monkeypatch, [""])
    assert _prompt.confirm("Create wiki?", default=True) is True


def test_confirm_reads_no(monkeypatch):
    _feed(monkeypatch, ["n"])
    assert _prompt.confirm("Create wiki?", default=True) is False


def test_checkbox_parses_comma_separated(monkeypatch):
    _feed(monkeypatch, ["claude, zed"])
    got = _prompt.checkbox("Clients", [("claude", "Claude Code"), ("zed", "Zed")],
                           checked=["claude"])
    assert got == ["claude", "zed"]


def test_checkbox_blank_line_keeps_pre_checked(monkeypatch):
    _feed(monkeypatch, [""])
    assert _prompt.checkbox("Clients", ["claude", "zed"], checked=["zed"]) == ["zed"]


def test_checkbox_dash_selects_nothing(monkeypatch):
    _feed(monkeypatch, ["-"])
    assert _prompt.checkbox("Clients", ["claude"], checked=["claude"]) == []


def test_checkbox_with_nothing_pre_checked_still_asks(monkeypatch):
    _feed(monkeypatch, ["zed"])
    assert _prompt.checkbox("Clients", ["claude", "zed"]) == ["zed"]


def test_checkbox_returns_values_not_labels(monkeypatch, capsys):
    _feed(monkeypatch, ["claude"])
    got = _prompt.checkbox("Clients", [("claude", "Claude Code"), ("zed", "Zed")],
                           checked=["zed"], hint="space to toggle")
    assert got == ["claude"]                          # value, not "Claude Code"
    out = capsys.readouterr().out
    assert "space to toggle" in out                   # hint survives, not markup
    assert "zed" in out                               # pre-checked = the default


def test_debug_explains_the_fallback(monkeypatch, capsys):
    from llm_wiki_base import _ui

    _ui.set_debug(True)
    _feed(monkeypatch, [""])
    _prompt.text("Wiki name", default="notes")
    assert "not a TTY" in capsys.readouterr().out
