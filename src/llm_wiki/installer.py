"""Idempotent install: merge MCP server config + symlink skills.

Cross-platform: macOS + Linux dùng symlink. Windows fallback `shutil.copytree` /
`shutil.copy2` nếu symlink fail (no Developer Mode / no admin).
"""
import json
import shutil
from pathlib import Path

from llm_wiki.base import get_base_dir, get_base_python
from llm_wiki.config import (
    CLIENT_PATHS,
    MCP_KEYS,
    get_mcp_config_path,
    get_skills_dir,
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


def install_centralized_mcp(
    client: str,
    server_name: str = CENTRALIZED_SERVER_NAME,
) -> Path:
    """Cài centralized MCP server entry cho 1 client (idempotent).

    Server này đọc registry.toml để biết các wiki có sẵn — không cần cài lại
    cho mỗi wiki. Ghi đè entry nếu đã tồn tại (overwrite bởi server_name).
    """
    base_dir = get_base_dir()
    cmd = centralized_server_cmd()
    env = centralized_server_env(base_dir)
    return install_mcp_config(client, server_name, cmd, env, cwd=str(base_dir))


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
) -> Path:
    """Merge 1 server entry vào client config JSON.

    Idempotent: nếu `server_name` đã tồn tại → ghi đè entry đó. KHÔNG phá server khác.
    Trả path tới file config đã ghi.
    """
    cfg_path = get_mcp_config_path(client)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if cfg_path.exists():
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    else:
        data = {}

    key = MCP_KEYS[client]
    servers = data.setdefault(key, {})

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
    return cfg_path


def install_skill(client: str, skill_name: str, source_dir: Path) -> Path | None:
    """Symlink (hoặc copy) 1 skill từ source → user-global skills dir.

    Claude Code: <skills_dir>/<name>/            → symlink dir → <source_dir>
    OpenCode:    <skills_dir>/<name>.md          → symlink file → <source_dir>/SKILL.md
    Zed:         bỏ qua (không có skill system).

    Fallback: nếu symlink fail (vd Windows no admin) → copy tree.
    Trả path tới link/copy đã tạo, hoặc None nếu client không hỗ trợ.
    """
    skills_dir = get_skills_dir(client)
    if skills_dir is None:
        return None
    skills_dir.mkdir(parents=True, exist_ok=True)

    source_dir = source_dir.resolve()
    if client == "claude":
        link = skills_dir / skill_name
    elif client == "opencode":
        link = skills_dir / f"{skill_name}.md"
    else:
        return None

    # Remove existing symlink/file/dir (idempotent re-install)
    if link.is_symlink() or link.exists():
        if link.is_symlink() or link.is_file():
            link.unlink()
        elif link.is_dir():
            shutil.rmtree(link)

    # Try symlink first
    try:
        if client == "claude":
            link.symlink_to(source_dir, target_is_directory=True)
        else:
            link.symlink_to(source_dir / "SKILL.md")
        return link
    except (OSError, NotImplementedError):
        # Windows: symlink cần Developer Mode hoặc admin → fallback copy
        if client == "claude":
            shutil.copytree(source_dir, link)
        else:
            shutil.copy2(source_dir / "SKILL.md", link)
        return link
