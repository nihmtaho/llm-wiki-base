"""Wiki registry — TOML file ánh xạ wiki name → path + type.

Registry nằm ở `<base_dir>/registry.toml`, quản lý bởi centralized MCP server
(`llm-wiki-base-mcp`) để biết được tất cả wikis có sẵn trên máy.

Format:
    # registry.toml
    [[wikis]]
    name = "my-knowledge"
    path = "/Users/me/my-knowledge"
    type = "personal"
    added = "2026-09-01T10:00:00"

    [[wikis]]
    name = "my-project-wiki"
    path = "/Users/me/projects/my-app/project-wiki"
    type = "project"
    added = "2026-09-01T10:00:00"
"""
import os
from datetime import datetime
from pathlib import Path

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

try:
    TOMLDecodeError = tomllib.TOMLDecodeError
except AttributeError:  # pragma: no cover
    TOMLDecodeError = Exception

from llm_wiki.base import get_base_dir

REGISTRY_FILE = "registry.toml"


def get_registry_path() -> Path:
    """Trả path tới registry.toml trong base dir."""
    return get_base_dir() / REGISTRY_FILE


def _empty() -> dict:
    """Return empty registry structure."""
    return {"wikis": []}


def load() -> dict:
    """Load registry. Trả dict có key 'wikis' = list of wiki entries.

    Trả về {'wikis': []} nếu file chưa tồn tại.
    """
    p = get_registry_path()
    if not p.exists():
        return _empty()
    with p.open("rb") as f:
        try:
            data = tomllib.load(f)
        except TOMLDecodeError:
            return _empty()
    if "wikis" not in data or not isinstance(data["wikis"], list):
        data["wikis"] = []
    return data


def save(data: dict) -> Path:
    """Ghi registry TOML (idempotent overwrite toàn bộ file)."""
    p = get_registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    wikis = data.get("wikis", [])
    for i, w in enumerate(wikis):
        lines.append(f"[[wikis]]")
        for k, v in w.items():
            if isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            else:
                lines.append(f'{k} = "{v}"')
        if i < len(wikis) - 1:
            lines.append("")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def add_wiki(name: str, path: str, wiki_type: str = "personal") -> None:
    """Thêm hoặc cập nhật 1 wiki trong registry (upsert theo name)."""
    data = load()
    wikis = data["wikis"]
    for w in wikis:
        if w.get("name") == name:
            w["path"] = str(path)
            w["type"] = wiki_type
            w["added"] = w.get("added", datetime.now().isoformat(timespec="seconds"))
            break
    else:
        wikis.append({
            "name": name,
            "path": str(path),
            "type": wiki_type,
            "added": datetime.now().isoformat(timespec="seconds"),
        })
    save(data)


def remove_wiki(name: str) -> bool:
    """Xóa wiki khỏi registry. Trả True nếu đã xóa."""
    data = load()
    before = len(data["wikis"])
    data["wikis"] = [w for w in data["wikis"] if w.get("name") != name]
    if len(data["wikis"]) != before:
        save(data)
        return True
    return False


def get_wiki(name: str) -> dict | None:
    """Tra wiki theo name. Trả dict {name, path, type, added} hoặc None."""
    for w in load()["wikis"]:
        if w.get("name") == name:
            return dict(w)
    return None


def list_wikis() -> list[dict]:
    """Liệt kê tất cả wikis trong registry."""
    return [dict(w) for w in load()["wikis"]]
