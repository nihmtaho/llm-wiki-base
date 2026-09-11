from typer.testing import CliRunner

from llm_wiki_base import __version__
from llm_wiki_base.cli import app


def test_version_command(runner: CliRunner):
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"llm-wiki-base {__version__}"


def test_version_flag(runner: CliRunner):
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"llm-wiki-base {__version__}"
