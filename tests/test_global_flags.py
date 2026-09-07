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
