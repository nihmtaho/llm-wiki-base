"""Idempotent install: merge MCP server config vào config file của AI client.

Skill linking nằm ở `_skills.link_clients()` (project-level symlink + prune) —
không ở đây, để chỉ có MỘT chỗ định nghĩa layout skill của từng client.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from llm_wiki.base import get_base_dir
from llm_wiki.config import (
    MCP_KEYS,
    get_mcp_config_path,
    get_project_mcp_path,
)

CENTRALIZED_SERVER_NAME = "llm-wiki-base-mcp"
CENTRALIZED_SERVER_SCRIPT = "mcp_base_server.py"


def centralized_server_cmd() -> list[str]:
    """Command cho centralized MCP server — qua `llm-wiki serve --mcp`.

    Entry trỏ vào CLI trên PATH (như `codegraph serve --mcp`) thay vì đường dẫn
    tuyệt đối tới base venv python: gọn, không vỡ khi user dời base dir hay
    reinstall venv. `serve` tự exec đúng base python + script, và setdefault
    LLM_WIKI_BASE_DIR lúc launch.
    """
    return ["llm-wiki", "serve", "--mcp"]


def centralized_server_env(base_dir: Path | None = None) -> dict:
    """Env cho centralized MCP server entry — luôn rỗng.

    `llm-wiki serve --mcp` đã setdefault LLM_WIKI_BASE_DIR lúc launch (env kế
    thừa > default) nên pin ở entry là thừa. KHÔNG pin retrieval env
    (WIKI_BM25_WEIGHT / WIKI_VEC_WEIGHT / WIKI_EMBED_MODEL): precedence là
    env > TOML, nên pin ở đây làm `.llm-wiki.toml` của user bị vô hiệu riêng
    trong MCP process (CLI vẫn tôn trọng) → cùng wiki, hai kết quả search
    khác nhau.
    """
    return {}


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
        return (f"{self.path}  [project: per-project/personal wiki, commit vào VCS được]  "
                f"key={self.key}.{self.server_name}")


def install_centralized_mcp(
    client: str,
    server_name: str = CENTRALIZED_SERVER_NAME,
    scope: str = "project",
    project_root: Path | None = None,
) -> McpInstall:
    """Cài centralized MCP server entry cho 1 client (idempotent).

    Ghi vào file MCP per-project/personal wiki (`<root>/.mcp.json`,
    `opencode.jsonc`, … — commit vào VCS được). Server này đọc registry.toml
    để biết các wiki có sẵn — không cần cài lại cho mỗi wiki. Ghi đè entry
    nếu đã tồn tại (overwrite bởi server_name).

    Args:
        scope: luôn 'project' (giữ param để không vỡ caller cũ truyền
            scope='project'; truyền 'user' → ValueError).
        project_root: root của wiki (personal) hoặc repo (project) — nơi chứa
            file MCP project-scope.

    Raises:
        ValueError: scope khác 'project', thiếu project_root, hoặc client
            không có project-scope MCP config.
    """
    if scope != "project":
        raise ValueError(f"llm-wiki chỉ cài MCP vào per-project/personal wiki "
                         f"(scope='project'), nhận: {scope!r}")
    base_dir = get_base_dir()
    cmd = centralized_server_cmd()
    env = centralized_server_env(base_dir)
    cwd = str(base_dir)

    if project_root is None:
        raise ValueError("cài MCP cần project_root (thư mục chứa wiki)")
    cfg_path = get_project_mcp_path(client, Path(project_root).resolve())
    if cfg_path is None:
        raise ValueError(
            f"{client} không có project-scope MCP config — bỏ qua client này")

    return install_mcp_config(client, server_name, cmd, env, cwd, cfg_path=cfg_path,
                              scope=scope)


def _build_mcp_entry(client: str, command: list[str], env: dict, cwd: str) -> dict:
    """Build MCP server entry theo schema của từng client.

    Key env (`env`/`environment`) chỉ ghi khi non-empty — entry của
    llm-wiki-base-mcp không pin env nào.
    """
    if client == "opencode":
        entry = {
            "type": "local",
            "command": command,
            "cwd": cwd,
            "enabled": True,
            "environment": env,
        }
    elif client == "zed":
        entry = {
            "command": command[0],
            "args": command[1:],
            "env": env,
        }
    elif client == "commandcode":
        # Schema stdio của Command Code: transport + enabled, KHÔNG có `cwd`.
        entry = {
            "transport": "stdio",
            "enabled": True,
            "command": command[0],
            "args": command[1:],
            "env": env,
        }
    else:
        # claude (và fallback cho client tương lai dùng shape "mcpServers")
        entry = {
            "command": command[0],
            "args": command[1:],
            "env": env,
            "cwd": cwd,
        }
    if not env:
        entry.pop("environment", None)
        entry.pop("env", None)
    return entry


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
