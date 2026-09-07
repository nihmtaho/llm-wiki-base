import re

from typer.testing import CliRunner

from llm_wiki_base.aliases import OLD_TO_NEW
from llm_wiki_base.cli import app

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


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _normalize(help_text: str, old: tuple[str, ...], new: tuple[str, ...]) -> str:
    """Compare help bodies ignoring the invocation path.

    Alias and canonical share one callback, so bodies are identical — only the
    invoked path differs (usage line, which newer renderers also print as a
    bare panel line with ANSI codes). Mask both paths (longest first so
    ("doctor",)/("setup", "doctor") pairs collapse correctly).
    """
    text = _ANSI_RE.sub("", help_text)
    for phrase in sorted((" ".join(old), " ".join(new)), key=len, reverse=True):
        text = text.replace(phrase, "<cmd>")
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("Usage:"))


def test_old_and_new_help_match(runner: CliRunner):
    for old, new in OLD_TO_NEW.items():
        old_help = runner.invoke(app, [*old, "--help"])
        new_help = runner.invoke(app, [*new, "--help"])
        assert old_help.exit_code == 0, old
        assert _normalize(old_help.output, old, new) == _normalize(new_help.output, old, new), old


def test_aliases_hidden_from_help(runner: CliRunner):
    top = runner.invoke(app, ["--help"]).output
    rows = [line.strip() for line in top.splitlines()]
    for old in OLD_TO_NEW:
        assert not any(r.startswith(old[0]) for r in rows), f"{old[0]} row visible in root help"
