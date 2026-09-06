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
