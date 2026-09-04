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


# Convention cho từng client.
#
# Init CHỈ ghi MCP vào file project-scope (`<root>/...`, commit vào VCS cho cả
# team) — không đụng file config cá nhân (user scope). `project_mcp` = None
# nghĩa là client đó chưa có file project-scope nào trong convention của nó
# (vd Zed) → init bỏ qua client đó kèm thông báo.
CLIENT_PATHS: dict[str, dict] = {
    "claude": {
        "config_dir": "claude",                  # lowercase everywhere
        "mcp_file": "mcp_servers.json",
        "skills_dir": "skills",
        "fallback_dir": Path.home() / ".claude", # legacy ~/ path
        "project_mcp": ".mcp.json",
    },
    "opencode": {
        "config_dir": "opencode",
        "mcp_file": "opencode.json",             # full config, key "mcp"
        "skills_dir": "commands",                # flat .md files
        "fallback_dir": Path.home() / ".opencode",
        "project_mcp": "opencode.jsonc",         # per-project wiki (commit được)
    },
    "zed": {
        "config_dir": "Zed",                     # capital Z (Apple HIG)
        "mcp_file": "settings.json",
        "skills_dir": None,                      # Zed dùng rules, không có skill system
        "fallback_dir": Path.home() / ".zed",
        "project_mcp": None,
    },
    "commandcode": {
        # Command Code KHÔNG dùng XDG/Application Support — config nằm thẳng ở home.
        "home_dir": ".commandcode",
        "mcp_file": "mcp.json",
        "skills_dir": None,                      # đọc `.agents/skills/` trực tiếp → không cần link
        "fallback_dir": Path.home() / ".commandcode",
        "project_mcp": ".mcp.json",
    },
}


def _resolve_with_fallback(client: str, key: str) -> Path | None:
    """Trả path tới file/dir cho client. None nếu key=None (vd: skills_dir của Zed)."""
    spec = CLIENT_PATHS[client]
    sub = spec.get(key)
    if sub is None:
        return None
    if spec.get("home_dir"):                      # client có config ở $HOME (commandcode)
        return Path.home() / spec["home_dir"] / sub
    conventional = user_config_base() / spec["config_dir"] / sub
    if conventional.parent.exists():
        return conventional
    return spec["fallback_dir"] / sub


def get_mcp_config_path(client: str) -> Path:
    """Trả path tới file MCP config (user scope) của client. Caller tự mkdir parent."""
    p = _resolve_with_fallback(client, "mcp_file")
    if p is None:
        raise ValueError(f"{client} has no MCP config file")
    return p


def get_project_mcp_path(client: str, project_root: Path) -> Path | None:
    """Path MCP config PROJECT scope (`<root>/.mcp.json`). None nếu client không có."""
    rel = CLIENT_PATHS[client].get("project_mcp")
    return project_root / rel if rel else None


def get_skills_dir(client: str) -> Path | None:
    """Trả path tới skills dir. None nếu client không có skill system (vd: Zed)."""
    return _resolve_with_fallback(client, "skills_dir")


def mcp_key(client: str) -> str:
    """Tên key trong file config chứa danh sách server của client."""
    return MCP_KEYS[client]


# MCP config key khác nhau giữa các client
MCP_KEYS: dict[str, str] = {
    "claude": "mcpServers",
    "opencode": "mcp",
    "zed": "context_servers",
    "commandcode": "mcpServers",
}


def supports_project_scope(client: str) -> bool:
    return bool(CLIENT_PATHS.get(client, {}).get("project_mcp"))


def supported_clients() -> list[str]:
    return list(CLIENT_PATHS.keys())
