from typer.testing import CliRunner

from llm_wiki.cli import app


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
