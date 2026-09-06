from typer.testing import CliRunner

from llm_wiki_base.cli import app


def _chdir_empty(monkeypatch, tmp_path):
    """Run the wizard in an empty dir so it never touches the repo checkout."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    monkeypatch.chdir(work)
    return work


def test_setup_personal_yes_runs_with_defaults(
    runner: CliRunner, isolated_env, tmp_path, monkeypatch
):
    _chdir_empty(monkeypatch, tmp_path)
    result = runner.invoke(
        app,
        ["setup", "personal", "--name", "demo", "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "home").exists()  # env actually isolated, sanity


def test_wizard_confirms_summary(runner: CliRunner, isolated_env, tmp_path, monkeypatch):
    _chdir_empty(monkeypatch, tmp_path)
    result = runner.invoke(app, ["setup"], input="personal\ndemo\nclaude\n\n")
    assert result.exit_code == 0, result.output
    assert "demo" in result.output  # summary screen echoed resolved values
