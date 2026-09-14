"""Install + remove for the clients whose config is not plain JSON.

These are the risky paths: codex (TOML) and hermes (YAML) are edited as text so
the owner's comments survive, and hermes is the one client allowed to write
OUTSIDE the wiki. Both must be reversible by `uninstall`.
"""
from pathlib import Path

import pytest

from llm_wiki_base import _blocks
from llm_wiki_base.installer import (
    CENTRALIZED_SERVER_NAME,
    find_our_mcp_entries,
    install_centralized_mcp,
    remove_mcp_entry,
    remove_our_mcp_entries,
)

KEY = "mcp_servers"


def _install(client, root, scope="project", server_name=CENTRALIZED_SERVER_NAME):
    return install_centralized_mcp(client, server_name=server_name,
                                   scope=scope, project_root=root)


# ── codex: TOML, project scope ──────────────────────────────────────────────

def test_codex_writes_a_toml_table(isolated_env, tmp_path):
    root = tmp_path / "repo"
    res = _install("codex", root)
    text = res.path.read_text(encoding="utf-8")
    assert res.path == root / ".codex" / "config.toml"
    assert f"[{KEY}.{CENTRALIZED_SERVER_NAME}]" in text
    assert 'command = "llm-wiki-base"' in text
    assert 'args = ["serve", "--mcp"]' in text
    assert f'cwd = "{isolated_env["base"]}"' in text
    _blocks.validate("toml", text)


def test_codex_keeps_the_project_owner_comments(isolated_env, tmp_path):
    root = tmp_path / "repo"
    cfg = root / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('# my codex settings\nmodel = "gpt-5-codex"\n', encoding="utf-8")
    _install("codex", root)
    text = cfg.read_text(encoding="utf-8")
    assert text.startswith("# my codex settings\nmodel = \"gpt-5-codex\"\n")
    _blocks.validate("toml", text)


def test_codex_install_is_idempotent(isolated_env, tmp_path):
    root = tmp_path / "repo"
    _install("codex", root)
    _install("codex", root)
    text = (root / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert text.count(f"[{KEY}.{CENTRALIZED_SERVER_NAME}]") == 1
    assert text.count(_blocks.BLOCK_BEGIN) == 1


def test_codex_remove_leaves_other_tables(isolated_env, tmp_path):
    root = tmp_path / "repo"
    cfg = root / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[mcp_servers.keepme]\ncommand = "npx"\n', encoding="utf-8")
    _install("codex", root)
    names, note, path = remove_mcp_entry("codex", root)
    assert (names, note) == ([CENTRALIZED_SERVER_NAME], "removed")
    text = path.read_text(encoding="utf-8")
    assert "keepme" in text and CENTRALIZED_SERVER_NAME not in text
    assert _blocks.BLOCK_BEGIN not in text
    _blocks.validate("toml", text)


def test_codex_dry_run_sees_the_entry(isolated_env, tmp_path):
    root = tmp_path / "repo"
    res = _install("codex", root)
    assert find_our_mcp_entries("codex", res.path) == [CENTRALIZED_SERVER_NAME]


# ── hermes: YAML, global only ───────────────────────────────────────────────

def test_hermes_has_no_project_scope(isolated_env, tmp_path):
    with pytest.raises(ValueError, match="project-scope"):
        _install("hermes", tmp_path / "repo")


def test_hermes_writes_global_config(isolated_env):
    res = _install("hermes", None, scope="user")
    assert res.path == Path(isolated_env["home"]) / ".hermes" / "config.yaml"
    text = res.path.read_text(encoding="utf-8")
    assert f"{KEY}:" in text
    assert f"  {CENTRALIZED_SERVER_NAME}:" in text
    assert "command: " in text
    assert "GLOBAL" in res.describe()          # the human is told where it landed
    _blocks.validate("yaml", text)


def test_hermes_keeps_existing_servers_and_comments(isolated_env):
    home = Path(isolated_env["home"])
    cfg = home / ".hermes" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(f"# hermes\n{KEY}:\n  context7:\n    command: npx\n", encoding="utf-8")
    _install("hermes", None, scope="user")
    text = cfg.read_text(encoding="utf-8")
    assert text.startswith("# hermes\n")
    assert "command: npx" in text
    assert text.count(f"{KEY}:") == 1
    _blocks.validate("yaml", text)


def test_hermes_remove_restores_the_file(isolated_env):
    """Hermes lives in user scope, so `uninstall` reaches it via the path directly
    (`remove_mcp_entry` only resolves project-scope files)."""
    home = Path(isolated_env["home"])
    cfg = home / ".hermes" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(f"{KEY}:\n  context7:\n    command: npx\n", encoding="utf-8")
    _install("hermes", None, scope="user")
    names, note = remove_our_mcp_entries("hermes", cfg)
    assert (names, note) == ([CENTRALIZED_SERVER_NAME], "removed")
    assert cfg.read_text(encoding="utf-8") == f"{KEY}:\n  context7:\n    command: npx\n"


def test_hermes_remove_deletes_the_file_we_created(isolated_env):
    home = Path(isolated_env["home"])
    _install("hermes", None, scope="user")
    cfg = home / ".hermes" / "config.yaml"
    names, note = remove_our_mcp_entries("hermes", cfg)
    assert note == "removed" and names
    assert not cfg.exists()


# ── the user-scope invariant ────────────────────────────────────────────────

@pytest.mark.parametrize("client", ["claude", "opencode", "commandcode", "zed",
                                    "pi", "cursor", "copilot", "codex"])
def test_only_flagged_clients_may_write_global(client, isolated_env, tmp_path):
    with pytest.raises(ValueError, match="project scope"):
        _install(client, tmp_path / "repo", scope="user")


# ── the 5 new JSON clients ──────────────────────────────────────────────────

def test_cursor_entry_declares_stdio_and_no_cwd(isolated_env, tmp_path):
    import json
    root = tmp_path / "repo"
    res = _install("cursor", root)
    entry = json.loads(res.path.read_text(encoding="utf-8"))["mcpServers"][CENTRALIZED_SERVER_NAME]
    assert res.path == root / ".cursor" / "mcp.json"
    assert entry["type"] == "stdio"
    assert "cwd" not in entry


def test_copilot_uses_the_servers_key(isolated_env, tmp_path):
    import json
    root = tmp_path / "repo"
    res = _install("copilot", root)
    data = json.loads(res.path.read_text(encoding="utf-8"))
    assert res.path == root / ".vscode" / "mcp.json"
    assert CENTRALIZED_SERVER_NAME in data["servers"]
    assert "mcpServers" not in data


def test_pi_shares_one_entry_with_claude(isolated_env, tmp_path):
    import json
    root = tmp_path / "repo"
    _install("claude", root)
    _install("pi", root)                      # same file, same server name
    data = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    assert list(data["mcpServers"]) == [CENTRALIZED_SERVER_NAME]


def test_zed_project_settings_is_written(isolated_env, tmp_path):
    import json
    root = tmp_path / "repo"
    res = _install("zed", root)
    assert res.path == root / ".zed" / "settings.json"
    entry = json.loads(res.path.read_text(encoding="utf-8"))["context_servers"][CENTRALIZED_SERVER_NAME]
    assert entry["command"] == "llm-wiki-base"
    assert "cwd" not in entry


def test_jsonc_client_with_comments_is_refused_not_overwritten(isolated_env, tmp_path):
    root = tmp_path / "repo"
    cfg = root / ".zed" / "settings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('// my zed prefs\n{\n  "theme": "zed_light"\n}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="comment"):
        _install("zed", root)
    assert cfg.read_text(encoding="utf-8").startswith("// my zed prefs")


def test_every_supported_client_resolves_a_target(isolated_env, tmp_path):
    from llm_wiki_base.config import supported_clients
    for client in supported_clients():
        try:
            _install(client, tmp_path / "repo")
        except ValueError as e:                # only the no-project-file case is allowed
            assert "project-scope" in str(e), client
