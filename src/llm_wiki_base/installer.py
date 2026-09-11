"""Idempotent install: merge MCP server config vào config file của AI client.

Skill linking nằm ở `_skills.link_clients()` (project-level symlink + prune) —
không ở đây, để chỉ có MỘT chỗ định nghĩa layout skill của từng client.

`remove_mcp_entry` là phép ngược của `install_mcp_config`: gỡ đúng entry của
llm-wiki-base (`server_name`) ra khỏi file config per-project/personal wiki, giữ
nguyên mọi server khác của user — dùng cho `llm-wiki-base uninstall`. Không bao
giờ sửa một file không parse được: thà báo để user tự xoá còn hơn làm hỏng config.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from llm_wiki_base.base import get_base_dir
from llm_wiki_base.config import (
    MCP_KEYS,
    get_mcp_config_path,
    get_project_mcp_path,
)

CENTRALIZED_SERVER_NAME = "llm-wiki-base-mcp"
CENTRALIZED_SERVER_SCRIPT = "mcp_base_server.py"


def centralized_server_cmd() -> list[str]:
    """Command cho centralized MCP server — qua `llm-wiki-base serve --mcp`.

    Entry trỏ vào CLI trên PATH (như `codegraph serve --mcp`) thay vì đường dẫn
    tuyệt đối tới base venv python: gọn, không vỡ khi user dời base dir hay
    reinstall venv. `serve` tự exec đúng base python + script, và setdefault
    LLM_WIKI_BASE_DIR lúc launch.
    """
    return ["llm-wiki-base", "serve", "--mcp"]


def centralized_server_env(base_dir: Path | None = None) -> dict:
    """Env cho centralized MCP server entry — luôn rỗng.

    `llm-wiki-base serve --mcp` đã setdefault LLM_WIKI_BASE_DIR lúc launch (env kế
    thừa > default) nên pin ở entry là thừa. KHÔNG pin retrieval env
    (WIKI_BM25_WEIGHT / WIKI_VEC_WEIGHT / WIKI_EMBED_MODEL): precedence là
    env > TOML, nên pin ở đây làm `.llm-wiki-base.toml` của user bị vô hiệu riêng
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
        raise ValueError(f"llm-wiki-base chỉ cài MCP vào per-project/personal wiki "
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
                f"llm-wiki-base KHÔNG tự ghi đè file hỏng") from None
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


# ─────────────────────────────────────────────────────────────────────────────
# Gỡ (phép ngược của cài) — phục vụ `llm-wiki-base uninstall`
# ─────────────────────────────────────────────────────────────────────────────

#: Dấu hiệu nhận entry DO llm-wiki-base ghi ra. So khớp trên toàn bộ command/args
#: (không chỉ phần tử đầu) vì entry cũ có thể pin đường dẫn tuyệt đối tới base
#: venv python (`~/.llm-wiki-base/tools/mcp_base_server.py`) thay vì `llm-wiki-base`
#: trên PATH, và `--server-name` tùy biến vẫn trỏ về cùng một lệnh — nên nhận diện
#: theo HÌNH của lệnh, không theo tên. Không đưa `mcp_server.py` trần vào: quá
#: chung, dễ dính server của user.
_OUR_MARKERS = ("llm-wiki-base", "mcp_base_server.py")


def _flatten_command(entry: dict) -> str:
    """Nối mọi phần tử `command` (list hoặc str) + `args` thành một chuỗi để dò marker."""
    parts: list[str] = []
    for field in ("command", "args"):
        val = entry.get(field)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            parts += [str(v) for v in val]
    return " ".join(parts)


def is_our_entry(entry: object) -> bool:
    """Entry này do llm-wiki-base tạo? = lệnh trỏ về CLI/script của ta.

    Nhận diện theo hình lệnh (không theo tên server) để: (a) bắt được entry cài
    bằng `--server-name` tùy biến; (b) KHÔNG bao giờ xoá nhầm server của user chỉ
    vì trùng tên — lệnh của họ không chứa marker của ta nên được giữ lại.
    """
    if not isinstance(entry, dict):
        return False
    return any(m in _flatten_command(entry) for m in _OUR_MARKERS)


def _load_servers(client: str, cfg_path: Path) -> tuple[dict | None, str, dict | None, str]:
    """Đọc file config MCP → (data, key, servers, note). data=None khi không sửa được.

    note ∈ {'absent', 'unreadable', 'no-key', 'ok'}. 'no-key' = file tốt nhưng
    không có mục servers của client này (hoặc không phải object).
    """
    key = MCP_KEYS[client]
    if not cfg_path.exists():
        return None, key, None, "absent"
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None, key, None, "unreadable"
    if not isinstance(data, dict):
        return None, key, None, "unreadable"
    servers = data.get(key)
    if not isinstance(servers, dict):
        return data, key, None, "no-key"
    return data, key, servers, "ok"


def find_our_mcp_entries(client: str, cfg_path: Path) -> list[str]:
    """Tên các server entry của llm-wiki-base trong 1 file config (read-only, dry-run)."""
    _data, _key, servers, note = _load_servers(client, cfg_path)
    if note != "ok" or servers is None:
        return []
    return [name for name, entry in servers.items() if is_our_entry(entry)]


def remove_our_mcp_entries(client: str, cfg_path: Path) -> tuple[list[str], str]:
    """Gỡ mọi entry MCP của llm-wiki-base khỏi 1 file config (mutating).

    Trả (removed_names, note) với note ∈ {'removed', 'absent', 'unreadable',
    'no-entry'}. Sau khi gỡ: servers rỗng → bỏ key container; file thành {}
    → xoá file (không còn config nào, để lại chỉ là rác). Không đụng file hỏng.
    """
    data, key, servers, note = _load_servers(client, cfg_path)
    if note != "ok" or data is None or servers is None:
        return [], ("no-entry" if note in ("no-key",) else note)
    removed = [name for name, entry in servers.items() if is_our_entry(entry)]
    if not removed:
        return [], "no-entry"
    for name in removed:
        servers.pop(name, None)
    if not servers:
        data.pop(key, None)
    if data:
        cfg_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    else:
        cfg_path.unlink()
    return removed, "removed"


def remove_mcp_entry(
    client: str,
    project_root: Path,
    server_name: str = CENTRALIZED_SERVER_NAME,
) -> tuple[list[str], str, Path | None]:
    """Gỡ entry MCP của llm-wiki-base khỏi file config project-scope của 1 client.

    Wrapper quanh remove_our_mcp_entries cho project scope (giữ chữ ký cũ cho
    caller). Trả (removed_names, note, cfg_path). `server_name` không dùng để
    quyết định gỡ — nhận diện theo hình lệnh để dọn cả entry cài bằng --server-name
    tùy biến (xem is_our_entry).
    """
    cfg_path = get_project_mcp_path(client, Path(project_root).resolve())
    if cfg_path is None:
        return [], "absent", None
    names, note = remove_our_mcp_entries(client, cfg_path)
    return names, note, cfg_path
