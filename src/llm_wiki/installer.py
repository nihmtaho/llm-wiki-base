"""Idempotent install: merge MCP server config vào config file của AI client.

Skill linking nằm ở `_skills.link_clients()` (project-level symlink + prune) —
không ở đây, để chỉ có MỘT chỗ định nghĩa layout skill của từng client.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from llm_wiki.base import get_base_dir, get_base_python
from llm_wiki.config import (
    MCP_KEYS,
    get_mcp_config_path,
    get_project_mcp_path,
)

CENTRALIZED_SERVER_NAME = "llm-wiki-base-mcp"
CENTRALIZED_SERVER_SCRIPT = "mcp_base_server.py"


def centralized_server_cmd() -> list[str]:
    """Build server command cho centralized MCP server (mcp_base_server.py in tools/)."""
    py_bin = get_base_python()
    base_dir = get_base_dir()
    script = base_dir / "tools" / CENTRALIZED_SERVER_SCRIPT
    return [str(py_bin), str(script)]


def centralized_server_env(base_dir: Path | None = None) -> dict:
    """Build env dict cho centralized MCP server.

    CHỈ đặt plumbing env. KHÔNG pin retrieval env (WIKI_BM25_WEIGHT /
    WIKI_VEC_WEIGHT / WIKI_EMBED_MODEL): precedence là env > TOML, nên pin ở
    đây làm `.llm-wiki.toml` của user bị vô hiệu riêng trong MCP process
    (CLI vẫn tôn trọng) → cùng wiki, hai kết quả search khác nhau.
    """
    bdir = base_dir or get_base_dir()
    return {
        "LLM_WIKI_BASE_DIR": str(bdir),
    }


@dataclass(frozen=True)
class McpInstall:
    """Kết quả cài MCP — để caller IN RA đúng vị trí + scope, không chỉ "installed".

    `__str__` = đường dẫn file, nên code cũ in `{cfg_path}` vẫn đúng.
    """
    client: str
    path: Path
    key: str          # key trong file config chứa danh sách server
    scope: str        # 'user' | 'project'
    server_name: str

    def __str__(self) -> str:  # noqa: D105
        return str(self.path)

    def describe(self) -> str:
        """Một dòng, đủ để user biết vừa sửa file nào và vào đâu trong file đó."""
        where = ("user scope — mọi project trên máy thấy"
                 if self.scope == "user"
                 else "project scope — chỉ repo này, commit vào VCS được")
        return f"{self.path}  [{self.scope}: {where}]  key={self.key}.{self.server_name}"


def install_centralized_mcp(
    client: str,
    server_name: str = CENTRALIZED_SERVER_NAME,
    scope: str = "user",
    project_root: Path | None = None,
) -> McpInstall:
    """Cài centralized MCP server entry cho 1 client (idempotent).

    Server này đọc registry.toml để biết các wiki có sẵn — không cần cài lại cho
    mỗi wiki. Ghi đè entry nếu đã tồn tại (overwrite bởi server_name).

    Args:
        scope: 'user' (file config cá nhân, mặc định) | 'project' (`.mcp.json` ở
            root repo, team dùng chung qua VCS).
        project_root: bắt buộc khi scope='project'.

    Raises:
        ValueError: scope lạ, thiếu project_root, hoặc client không có project scope.
    """
    if scope not in ("user", "project"):
        raise ValueError(f"mcp-scope phải là 'user' hoặc 'project', nhận: {scope!r}")
    base_dir = get_base_dir()
    cmd = centralized_server_cmd()
    env = centralized_server_env(base_dir)
    cwd = str(base_dir)

    if scope == "project":
        if project_root is None:
            raise ValueError("scope='project' cần project_root")
        cfg_path = get_project_mcp_path(client, Path(project_root).resolve())
        if cfg_path is None:
            raise ValueError(
                f"{client} không có project-scope MCP config — dùng --mcp-scope user")
    else:
        cfg_path = get_mcp_config_path(client)

    return install_mcp_config(client, server_name, cmd, env, cwd, cfg_path=cfg_path,
                              scope=scope)


def _build_mcp_entry(client: str, command: list[str], env: dict, cwd: str) -> dict:
    """Build MCP server entry theo schema của từng client."""
    if client == "opencode":
        return {
            "type": "local",
            "command": command,
            "cwd": cwd,
            "enabled": True,
            "environment": env,
        }
    if client == "zed":
        return {
            "command": command[0],
            "args": command[1:],
            "env": env,
        }
    if client == "commandcode":
        # Schema stdio của Command Code: transport + enabled, KHÔNG có `cwd`.
        # Không cần cwd vì command + args là đường dẫn tuyệt đối và base dir đã
        # truyền qua env LLM_WIKI_BASE_DIR.
        return {
            "transport": "stdio",
            "enabled": True,
            "command": command[0],
            "args": command[1:],
            "env": env,
        }
    # claude (và fallback cho client tương lai dùng shape "mcpServers")
    return {
        "command": command[0],
        "args": command[1:],
        "env": env,
        "cwd": cwd,
    }


def install_mcp_config(
    client: str,
    server_name: str,
    command: list[str],
    env: dict,
    cwd: str,
    cfg_path: Path | None = None,
    scope: str = "user",
) -> McpInstall:
    """Merge 1 server entry vào client config JSON.

    Idempotent: nếu `server_name` đã tồn tại → ghi đè entry đó. KHÔNG phá server khác.
    Trả `McpInstall` (path + key + scope) để caller in ra vị trí thật.
    """
    cfg_path = cfg_path or get_mcp_config_path(client)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise ValueError(
                f"{cfg_path} không phải JSON hợp lệ ({e}) — sửa file tay rồi chạy lại, "
                f"llm-wiki KHÔNG tự ghi đè file hỏng") from None
        if not isinstance(data, dict):
            raise ValueError(f"{cfg_path} phải là JSON object, đang là {type(data).__name__}")
    else:
        data = {}

    key = MCP_KEYS[client]
    servers = data.setdefault(key, {})
    if not isinstance(servers, dict):
        raise ValueError(f"{cfg_path}: key {key!r} không phải object — không ghi được")

    # Detect overwrite với cwd khác — cảnh báo cho caller
    prev = servers.get(server_name)
    if prev and isinstance(prev, dict) and prev.get("cwd") and prev["cwd"] != cwd:
        import warnings
        warnings.warn(
            f"{client}: MCP server '{server_name}' đã tồn tại với cwd={prev['cwd']!r}, "
            f"đang ghi đè với cwd={cwd!r}",
            stacklevel=2,
        )

    servers[server_name] = _build_mcp_entry(client, command, env, cwd)
    cfg_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return McpInstall(client=client, path=cfg_path, key=key, scope=scope,
                      server_name=server_name)
