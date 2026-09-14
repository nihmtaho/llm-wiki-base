"""Cross-platform user-global config paths for AI clients.

Resolve MCP config + skills dir cho các AI client đã hỗ trợ trên Win/macOS/Linux.
Mỗi client có 1 path "conventional" (theo XDG / OS standard) và 1 path "fallback"
(legacy `~/.{client}/`). Hàm `get_*` thử conventional trước, fallback nếu dir cha
không tồn tại — handle case khi user chưa cài client.

Mọi path liên quan tới HOME đều dựng từ chuỗi (KHÔNG phải `Path` đóng băng lúc
import): `Path.home()` evaluated at import would capture whatever HOME was then,
which quietly breaks `monkeypatch.setenv("HOME", ...)` in tests. Detection in
`clients.py` needs the same laziness.
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


# Convention cho từng client — MỘT nguồn sự thật cho: đường dẫn, key chứa danh
# sách server, hình entry, và cách dò xem client có trên máy (`detect`).
#
# Init CHỈ ghi MCP vào file project-scope (`<root>/.mcp.json`, `.zed/settings.json`,
# … commit vào VCS cho cả team) — không đụng file config cá nhân (user scope).
# `project_mcp` = None nghĩa là client đó không có file project-scope nào trong
# convention của nó (vd Hermes: chỉ `~/.hermes/config.yaml`) → muốn cài phải ghi
# global, nên cần `allow_user_scope = True` để nói rõ là có ngoại lệ.
#
# `detect` là bằng chứng "client này có thật trên máy": binaries probe qua PATH,
# paths probe existence (chain `~` tự expand), apps chỉ dùng trên macOS.
# `format`: "json" = merge cấu trúc an toàn; "toml"/"yaml" = KHÔNG round-trip
# (sẽ nướng sạch comment của user) → ghi bằng managed block, xem installer.py.
CLIENT_PATHS: dict[str, dict] = {
    "claude": {
        "label": "Claude Code",
        "config_dir": "claude",                  # lowercase everywhere
        "mcp_file": "mcp_servers.json",
        "mcp_key": "mcpServers",
        "skills_dir": "skills",
        "fallback_rel": ".claude",               # legacy ~/ path
        "project_mcp": ".mcp.json",
        "format": "json",
        "detect": {
            "binaries": ["claude"],
            "paths": ["~/.claude", "~/.claude.json", "~/.config/claude"],
            "apps": [],
        },
    },
    "opencode": {
        "label": "OpenCode",
        "config_dir": "opencode",
        "mcp_file": "opencode.json",             # full config, key "mcp"
        "mcp_key": "mcp",
        "skills_dir": "commands",                # flat .md files
        "fallback_rel": ".opencode",
        "project_mcp": "opencode.jsonc",         # per-project wiki (commit được)
        "format": "json",
        "detect": {
            "binaries": ["opencode"],
            "paths": ["~/.config/opencode", "~/.opencode"],
            "apps": [],
        },
    },
    "zed": {
        "label": "Zed",
        "config_dir": "Zed",                     # capital Z (Apple HIG)
        "mcp_file": "settings.json",
        "mcp_key": "context_servers",
        "skills_dir": None,                      # Zed dùng rules, không có skill system
        "fallback_rel": ".zed",
        "project_mcp": ".zed/settings.json",     # project settings, cùng key
        "format": "json",
        "detect": {
            "binaries": ["zed"],
            "paths": ["~/.config/zed", "~/.zed", "~/Library/Application Support/Zed"],
            "apps": ["Zed"],
        },
    },
    "commandcode": {
        "label": "Command Code",
        # Command Code KHÔNG dùng XDG/Application Support — config nằm thẳng ở home.
        "home_dir": ".commandcode",
        "mcp_file": "mcp.json",
        "mcp_key": "mcpServers",
        "skills_dir": None,                      # đọc `.agents/skills/` trực tiếp → không cần link
        "fallback_rel": ".commandcode",
        "project_mcp": ".mcp.json",
        "format": "json",
        "detect": {
            "binaries": ["commandcode"],
            "paths": ["~/.commandcode"],
            "apps": [],
        },
    },
    "pi": {
        "label": "Pi (pi-mcp-adapter)",
        # Pi lấy `.mcp.json` làm project config preferred → dùng chung file với
        # claude/commandcode; `mcpServers` là key chuẩn của adapter.
        "home_dir": ".pi",
        "mcp_file": "agent/mcp.json",
        "mcp_key": "mcpServers",
        "skills_dir": None,                      # adapter đọc .agents/skills/ qua Pi
        "fallback_rel": ".pi",
        "project_mcp": ".mcp.json",
        "format": "json",
        "detect": {
            "binaries": ["pi"],
            "paths": ["~/.pi", "~/.config/mcp", "~/.agents"],
            "apps": [],
        },
    },
    "cursor": {
        "label": "Cursor",
        "home_dir": ".cursor",
        "mcp_file": "mcp.json",
        "mcp_key": "mcpServers",
        "skills_dir": None,
        "fallback_rel": ".cursor",
        "project_mcp": ".cursor/mcp.json",
        "format": "json",
        "detect": {
            "binaries": ["cursor"],
            "paths": ["~/.cursor"],
            "apps": ["Cursor"],
        },
    },
    "copilot": {
        "label": "GitHub Copilot (VS Code)",
        # VS Code chỉ có project file `.vscode/mcp.json`, và key của nó là `servers`
        # (KHÔNG phải `mcpServers`). User scope nằm trong settings.json lồng nhau
        # → để mcp_file = None: mọi ý định ghi/gỡ user-scope phải báo lỗi rõ ràng.
        "config_dir": "Code",
        "mcp_file": None,
        "mcp_key": "servers",
        "skills_dir": None,
        "fallback_rel": ".vscode",
        "project_mcp": ".vscode/mcp.json",
        "format": "json",
        "detect": {
            "binaries": ["code", "copilot"],
            "paths": ["~/.vscode", "~/.vscode-server"],
            "apps": ["Visual Studio Code", "Visual Studio Code - Insiders"],
        },
    },
    "codex": {
        "label": "Codex",
        "home_dir": ".codex",
        "mcp_file": "config.toml",
        "mcp_key": "mcp_servers",
        "skills_dir": None,
        "fallback_rel": ".codex",
        # Project scope được, nhưng Codex chỉ đọc `.codex/config.toml` khi project
        # đã được trust → setup xong vẫn cần approve trong Codex (xem docs/mcp.md).
        "project_mcp": ".codex/config.toml",
        "format": "toml",
        "detect": {
            "binaries": ["codex"],
            "paths": ["~/.codex"],
            "apps": [],
        },
    },
    "hermes": {
        "label": "Hermes Agent",
        "home_dir": ".hermes",
        "mcp_file": "config.yaml",
        "mcp_key": "mcp_servers",
        "skills_dir": None,
        "fallback_rel": ".hermes",
        "project_mcp": None,                     # Hermes chỉ có config người dùng
        "allow_user_scope": True,                # → ghi global, wizard phải nói rõ
        "format": "yaml",
        "detect": {
            "binaries": ["hermes"],
            "paths": ["~/.hermes"],
            "apps": [],
        },
    },
}


def client_spec(client: str) -> dict:
    """Full convention record for `client`.

    Raises:
        KeyError: client not in the table (caller maps it to "unsupported
            client" — the table IS the allow-list).
    """
    return CLIENT_PATHS[client]


def client_label(client: str) -> str:
    """Display name for menus and panels ("Claude Code"), falling back to the key."""
    return CLIENT_PATHS.get(client, {}).get("label") or client


def client_format(client: str) -> str:
    """'json' | 'toml' | 'yaml' — decides merge strategy in installer."""
    return CLIENT_PATHS.get(client, {}).get("format", "json")


def supports_user_scope(client: str) -> bool:
    """Client without any project-scope file, so it can only be installed globally."""
    return bool(CLIENT_PATHS.get(client, {}).get("allow_user_scope"))


#: MCP config key khác nhau giữa các client — dẫn xuất từ bảng trên để không bao
#: giờ có hai chỗ nói khác nhau về cùng một client.
MCP_KEYS: dict[str, str] = {c: spec["mcp_key"] for c, spec in CLIENT_PATHS.items()}


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
    return Path.home() / spec["fallback_rel"] / sub


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


def supports_project_scope(client: str) -> bool:
    return bool(CLIENT_PATHS.get(client, {}).get("project_mcp"))


def supported_clients() -> list[str]:
    return list(CLIENT_PATHS.keys())
