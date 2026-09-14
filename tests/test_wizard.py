"""The setup wizard asks with menus, and the client list comes from the machine.

Wizard answers are fed through the non-TTY fallback (typed names or numbers),
which is also what CI and `curl | sh` scripts hit.
"""
import json
from pathlib import Path

from typer.testing import CliRunner

from llm_wiki_base.cli import app


def _chdir_empty(monkeypatch, tmp_path):
    """Run the wizard in an empty dir so it never touches the repo checkout."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    monkeypatch.chdir(work)
    return work


def _wide(monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")


# menu order comes from CLIENT_PATHS; these numbers are what a typed answer maps to
CLAUDE, OPENCODE, ZED, COMMANDCODE, PI, CURSOR, COPILOT, CODEX, HERMES = range(1, 10)


def test_setup_personal_yes_runs_with_defaults(
    runner: CliRunner, isolated_env, machine, tmp_path, monkeypatch
):
    work = _chdir_empty(monkeypatch, tmp_path)
    machine("claude")
    result = runner.invoke(app, ["setup", "personal", "--name", "demo", "--yes"])
    assert result.exit_code == 0, result.output
    assert (work / ".mcp.json").is_file()           # the one detected client got it
    assert (tmp_path / "home").exists()             # env actually isolated, sanity


def test_wizard_confirms_summary(runner: CliRunner, isolated_env, machine,
                                 tmp_path, monkeypatch):
    _chdir_empty(monkeypatch, tmp_path)
    machine("claude")
    result = runner.invoke(app, ["setup"], input="personal\ndemo\nclaude\n\n")
    assert result.exit_code == 0, result.output
    assert "demo" in result.output                  # summary echoed resolved values


def test_wizard_lists_clients_with_evidence(runner: CliRunner, isolated_env, machine,
                                            tmp_path, monkeypatch):
    _chdir_empty(monkeypatch, tmp_path)
    _wide(monkeypatch)
    machine("claude")
    result = runner.invoke(app, ["setup"],
                           input=f"personal\ndemo\n{CLAUDE}\n\n")
    out = result.output
    assert result.exit_code == 0, out
    assert "Claude Code" in out                     # detected: named, pre-checked
    assert "not detected" in out                    # others still listed, with reason
    assert "Hermes" in out                          # all 9 are selectable


def test_wizard_accepts_numeric_answers(runner: CliRunner, isolated_env, machine,
                                        tmp_path, monkeypatch):
    work = _chdir_empty(monkeypatch, tmp_path)
    machine("claude", "codex")
    result = runner.invoke(app, ["setup"],
                           input=f"personal\ndemo\n{CLAUDE},{CODEX}\n\n")
    assert result.exit_code == 0, result.output
    assert (work / ".mcp.json").is_file()
    assert (work / ".codex" / "config.toml").is_file()
    assert not (work / ".vscode").exists()          # unselected clients untouched


def test_wizard_empty_selection_creates_wiki_without_mcp(
        runner: CliRunner, isolated_env, machine, tmp_path, monkeypatch):
    work = _chdir_empty(monkeypatch, tmp_path)
    _wide(monkeypatch)
    machine("claude")
    result = runner.invoke(app, ["setup"], input="personal\ndemo\n-\n\n")
    assert result.exit_code == 0, result.output
    assert not (work / ".mcp.json").exists()
    assert work.is_dir() and (work / "wiki").is_dir()   # the wiki itself is still made
    assert "(none)" in result.output


def test_setup_without_c_uses_detection(machine, runner: CliRunner, isolated_env,
                                        tmp_path, monkeypatch):
    work = _chdir_empty(monkeypatch, tmp_path)
    machine("claude", "codex", "copilot")
    result = runner.invoke(app, ["setup", "personal", "-n", "demo", "-y"])
    assert result.exit_code == 0, result.output
    assert (work / ".mcp.json").is_file()
    assert (work / ".codex" / "config.toml").is_file()
    assert (work / ".vscode" / "mcp.json").is_file()


def test_explicit_client_flag_ignores_detection(machine, runner: CliRunner,
                                                isolated_env, tmp_path, monkeypatch):
    work = _chdir_empty(monkeypatch, tmp_path)
    machine("claude", "codex")
    result = runner.invoke(app, ["setup", "personal", "-n", "demo", "-c", "claude", "-y"])
    assert result.exit_code == 0, result.output
    assert not (work / ".codex").exists()


def test_nothing_detected_still_offers_every_client(machine, runner: CliRunner,
                                                    isolated_env, tmp_path, monkeypatch):
    work = _chdir_empty(monkeypatch, tmp_path)
    _wide(monkeypatch)
    machine()                                        # empty PATH, empty HOME
    result = runner.invoke(app, ["setup", "personal", "-n", "demo", "-y"])
    assert result.exit_code == 0, result.output
    assert not (work / ".mcp.json").exists()        # nothing guessed on our behalf
    assert "không có client nào được chọn" in result.output

    pick = runner.invoke(app, ["setup"], input=f"personal\ndemo\n{OPENCODE}\n\n")
    assert pick.exit_code == 0, pick.output
    assert (work / "opencode.jsonc").is_file()      # ... but the human can still choose


def test_unknown_client_is_rejected_before_anything_is_written(
        runner: CliRunner, isolated_env, machine, tmp_path, monkeypatch):
    work = _chdir_empty(monkeypatch, tmp_path)
    _wide(monkeypatch)
    machine("claude")
    result = runner.invoke(app, ["setup", "personal", "-n", "demo", "-c", "gemini", "-y"])
    assert result.exit_code == 1
    assert "unsupported client 'gemini'" in result.output
    assert list(work.iterdir()) == []               # no half-made wiki


def test_hermes_is_installed_globally_and_says_so(runner: CliRunner, isolated_env,
                                                  machine, tmp_path, monkeypatch):
    work = _chdir_empty(monkeypatch, tmp_path)
    _wide(monkeypatch)
    machine("hermes")
    result = runner.invoke(app, ["setup", "personal", "-n", "demo", "-c", "hermes", "-y"])
    assert result.exit_code == 0, result.output
    cfg = Path(isolated_env["home"]) / ".hermes" / "config.yaml"
    assert cfg.is_file()
    assert not any(work.rglob("*.yaml"))            # nothing claimed to be in the wiki
    assert "GLOBAL" in result.output


def test_zed_uses_its_own_project_settings_file(runner: CliRunner, isolated_env,
                                                machine, tmp_path, monkeypatch):
    work = _chdir_empty(monkeypatch, tmp_path)
    machine("zed")
    result = runner.invoke(app, ["setup", "personal", "-n", "demo", "-c", "zed", "-y"])
    assert result.exit_code == 0, result.output
    data = json.loads((work / ".zed" / "settings.json").read_text(encoding="utf-8"))
    assert data["context_servers"]["llm-wiki-base-mcp"]["command"] == "llm-wiki-base"


def test_setup_clients_lists_every_option(machine, runner: CliRunner, isolated_env,
                                          tmp_path, monkeypatch):
    _wide(monkeypatch)
    machine("claude", "pi")
    result = runner.invoke(app, ["setup", "clients"])
    assert result.exit_code == 0, result.output
    from llm_wiki_base.config import client_label, supported_clients
    for client in supported_clients():
        assert client_label(client) in result.output       # every option is named
    assert "-c claude -c pi" in result.output              # only what was detected
    assert "-c zed" not in result.output


def test_doctor_reports_client_detection(machine, runner: CliRunner, isolated_env,
                                         tmp_path, monkeypatch):
    _wide(monkeypatch)
    machine("claude")
    work = _chdir_empty(monkeypatch, tmp_path)
    result = runner.invoke(app, ["setup", "doctor", "--root", str(work)])
    assert "AI clients" in result.output
    assert "binary" in result.output                # evidence, not just yes/no
