"""Cross-platform user-global config paths for AI clients.

Resolve MCP config + skills dir cho Claude Code, OpenCode, Zed trên Win/macOS/Linux.
Mỗi client có 1 path "conventional" (theo XDG / OS standard) và 1 path "fallback"
(legacy `~/.{client}/`). Hàm `get_*` thử conventional trước, fallback nếu dir cha
không tồn tại — handle case khi user chưa cài client.
"""
import os
import sys
from pathlib import Path


def user_config_base() -> Path:
    """Base dir cho user config theo OS convention.

    macOS  → ~/Library/Application Support
    Windows → %APPDATA%
    Linux  → $XDG_CONFIG_HOME (default ~/.config)

    Return Path luôn là absolute.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    # linux + others
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


# Convention cho từng client. App name casing tuỳ OS (capitalized trên macOS theo Apple HIG).
CLIENT_PATHS: dict[str, dict] = {
    "claude": {
        "config_dir": "claude",                  # lowercase everywhere
        "mcp_file": "mcp_servers.json",
        "skills_dir": "skills",
        "fallback_dir": Path.home() / ".claude", # legacy ~/ path
    },
    "opencode": {
        "config_dir": "opencode",
        "mcp_file": "opencode.json",             # full config, key "mcp"
        "skills_dir": "commands",                # flat .md files
        "fallback_dir": Path.home() / ".opencode",
    },
    "zed": {
        "config_dir": "Zed",                     # capital Z (Apple HIG)
        "mcp_file": "settings.json",
        "skills_dir": None,                      # Zed dùng rules, không có skill system
        "fallback_dir": Path.home() / ".zed",
    },
}


def _resolve_with_fallback(client: str, key: str) -> Path | None:
    """Trả path tới file/dir cho client. None nếu key=None (vd: Zed skills_dir)."""
    spec = CLIENT_PATHS[client]
    sub = spec.get(key)
    if sub is None:
        return None
    conventional = user_config_base() / spec["config_dir"] / sub
    if conventional.parent.exists():
        return conventional
    return spec["fallback_dir"] / sub


def get_mcp_config_path(client: str) -> Path:
    """Trả path tới file MCP config của client. Tạo parent dir nếu cần (caller mkdir)."""
    p = _resolve_with_fallback(client, "mcp_file")
    if p is None:
        raise ValueError(f"{client} has no MCP config file")
    return p


def get_skills_dir(client: str) -> Path | None:
    """Trả path tới skills dir. None nếu client không có skill system (vd: Zed)."""
    return _resolve_with_fallback(client, "skills_dir")


# MCP config key khác nhau giữa các client
MCP_KEYS: dict[str, str] = {
    "claude": "mcpServers",
    "opencode": "mcp",
    "zed": "context_servers",
}


def supported_clients() -> list[str]:
    return list(CLIENT_PATHS.keys())
