from typer.testing import CliRunner
from llm_wiki.cli import app


def test_canonical_groups_exist(runner: CliRunner):
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in ["setup", "wiki", "check", "review", "translate", "config"]:
        assert group in result.output


def test_check_lint_reachable(runner: CliRunner, isolated_env):
    result = runner.invoke(app, ["check", "lint", "--help"])
    assert result.exit_code == 0
