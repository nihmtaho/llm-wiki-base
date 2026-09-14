"""Detection must be proven from the filesystem, never assumed from defaults.

Each test builds a fake HOME (and sometimes a fake PATH) so the probes see a
machine that either has or has not got a client — and so nothing here can touch
the real user config.
"""
from pathlib import Path

import pytest

from llm_wiki_base import clients


@pytest.fixture()
def empty_home(tmp_path, monkeypatch):
    """A home where no client is installed, nothing is on PATH, no app bundles."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setattr(clients, "APPS_ROOT", tmp_path / "no-applications")
    return home


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def _binary(tmp_path, monkeypatch, name: str) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / name
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir))


def test_every_supported_client_is_reported(empty_home):
    states = clients.detect(empty_home)
    assert [s.key for s in states] == list(clients.CLIENT_PATHS)
    assert all(s.label for s in states)


def test_clean_machine_detects_nothing(empty_home):
    assert clients.detected_keys(clients.detect(empty_home)) == []
    for state in clients.detect(empty_home):
        assert not state.detected
        # "not detected" alone is not an answer — say what was probed.
        assert "not detected" in state.evidence
        assert "'" in state.evidence or "~/" in state.evidence


def test_config_dir_counts_as_installed(empty_home):
    (empty_home / ".commandcode").mkdir()
    assert clients.detected_keys(clients.detect(empty_home)) == ["commandcode"]


def test_legacy_home_dotfile_counts(empty_home):
    """Claude's `~/.claude.json` proves the client exists even with no dir."""
    _touch(empty_home / ".claude.json")
    assert clients.detected_keys(clients.detect(empty_home)) == ["claude"]


def test_binary_on_path_is_enough(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "no-such-home"))
    _binary(tmp_path, monkeypatch, "claude")
    state = clients.probe("claude")
    assert state.detected and state.evidence.startswith("binary")


def test_config_path_used_when_no_binary(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    _touch(home / ".config" / "opencode" / "opencode.json")
    state = clients.probe("opencode")
    assert state.detected and state.evidence.startswith("config")
    assert state.evidence.endswith("~/.config/opencode")


def test_home_is_read_at_call_time(tmp_path, monkeypatch):
    """Regression: CLIENT_PATHS must not freeze Path.home() at import.

    The first probe sees the empty home, the second sees one where claude was
    created — if any path had been resolved at import, the second would still
    report "not detected".
    """
    home_a = tmp_path / "a"
    home_b = tmp_path / "b"
    home_a.mkdir()
    home_b.mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setenv("HOME", str(home_a))
    assert clients.probe("claude").detected is False
    monkeypatch.setenv("HOME", str(home_b))
    _touch(home_b / ".claude" / "skills")
    assert clients.probe("claude").detected is True


def test_paths_given_to_probe_win_over_env(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    _touch(home / ".claude.json")
    assert clients.probe("claude", home=home).detected is True


def test_choices_label_checked_and_unclelected(empty_home):
    (empty_home / ".claude").mkdir()
    states = clients.detect(empty_home)
    picked = dict(clients.choices(states))
    assert picked["claude"].startswith("[✓] Claude Code")
    assert picked["opencode"].startswith("[?] OpenCode")
    assert "not detected" in picked["opencode"]


def test_rows_for_doctor_have_four_columns(empty_home):
    rows = clients.as_rows(clients.detect(empty_home))
    assert all(len(r) == 4 for r in rows)
    assert rows[0][1] in ("yes", "no")


def test_flags_round_trip_back_into_dash_c(empty_home):
    assert clients.client_flags(["claude", "zed"]) == "-c claude -c zed"


def test_every_supported_client_names_a_file_to_write(empty_home):
    """A menu row that says "detected" must also say what it will touch."""
    for state in clients.detect(empty_home):
        assert state.target
        assert state.scope in ("project", "global")


def test_app_bundle_alone_counts(tmp_path, monkeypatch, empty_home):
    """An IDE installed as an app but never launched still has no config dir."""
    apps = tmp_path / "Applications"
    (apps / "Zed.app").mkdir(parents=True)
    monkeypatch.setattr(clients, "APPS_ROOT", apps)
    monkeypatch.setattr(clients.sys, "platform", "darwin")
    state = clients.probe("zed", home=empty_home)
    assert state.detected and state.evidence.endswith("Zed.app")


def test_app_bundle_ignored_off_macos(tmp_path, monkeypatch, empty_home):
    apps = tmp_path / "Applications"
    (apps / "Zed.app").mkdir(parents=True)
    monkeypatch.setattr(clients, "APPS_ROOT", apps)
    monkeypatch.setattr(clients.sys, "platform", "linux")
    assert clients.probe("zed", home=empty_home).detected is False


def test_zed_writes_project_settings(empty_home):
    """Zed accepts context_servers in project settings — no need to touch global."""
    state = clients.probe("zed", home=empty_home)
    assert state.scope == "project"
    assert state.target == ".zed/settings.json"


def test_user_scope_only_for_clients_without_project_file(empty_home):
    from llm_wiki_base.config import supports_project_scope, supports_user_scope
    for client in clients.CLIENT_PATHS:
        assert not (supports_project_scope(client) and supports_user_scope(client))
