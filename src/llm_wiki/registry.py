"""Wiki registry — TOML file ánh xạ wiki name → id + path + type.

Registry nằm ở `<base_dir>/registry.toml`, quản lý bởi centralized MCP server
(`llm-wiki-base-mcp`) để biết được tất cả wikis có sẵn trên máy.

Format:
    # registry.toml
    [[wikis]]
    name = "my-knowledge"                 # key tra cứu — dùng làm tham số `wiki=`
    id = "b41c2f9a7d3e4a11"               # UUID ổn định — không đổi khi đổi tên/folder
    path = "/Users/me/my-knowledge"
    type = "personal"
    added = "2026-09-01T10:00:00"

Vì sao có cả `name` lẫn `id`: `name` là thứ con người gõ vào `wiki=` và vào
`llm-wiki wiki remove`, nên nó phải dễ đọc. `id` là danh tính máy — cần để phát
hiện "hai wiki khác nhau cùng tên", vốn đã xảy ra thật (2 project wiki cùng tên
`wiki` vì init lấy tên theo subfolder, và upsert theo name đá wiki đầu khỏi
registry im lặng). Giờ trùng tên khác path → tự thêm hậu tố `-<uuid8>`.
"""
import os
import uuid
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
    """Path tới registry.toml.

    Override bằng env `LLM_WIKI_REGISTRY` (file tuyệt đối) — cần cho test/script chạy
    với registry tạm thời. `llm-wiki init --no-register` là cách khác để không ghi vào
    registry thật: init trước đây luôn auto-đăng ký, nên mấy lần test đã làm bẩn
    registry của người dùng (xem docs/session/session-tier3-retrieval-2026-09-02.md §7b).
    """
    override = os.environ.get("LLM_WIKI_REGISTRY")
    if override:
        return Path(override).expanduser().resolve()
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


def new_id() -> str:
    """UUID rút gọn 12 hex — đủ để không đụng, đủ ngắn để đọc trong log."""
    return uuid.uuid4().hex[:12]


def _backfill_ids(data: dict) -> bool:
    """Thêm `id` cho entry cũ chưa có. Trả True nếu có sửa."""
    changed = False
    for w in data["wikis"]:
        if not w.get("id"):
            w["id"] = new_id()
            changed = True
    return changed


def add_wiki(name: str, path: str, wiki_type: str = "personal") -> str:
    """Đăng ký / cập nhật 1 wiki. Trả về name ĐƯỢC DÙNG (có thể khác `name` xin vào).

    Ba trường hợp:
      - trùng name + trùng path  → re-init: giữ nguyên id + added, chỉ cập nhật type.
      - trùng name + khác path   → không đá nhau: thêm hậu tố `-<uuid8>` vào tên mới.
      - chưa trùng               → thêm entry, gán id.
    """
    data = load()
    wikis = data["wikis"]
    want, target = name.strip(), os.path.normpath(str(path))

    same_path = next((w for w in wikis
                      if os.path.normpath(str(w.get("path", ""))) == target), None)
    if same_path is not None:                       # re-init cùng folder
        if name and same_path.get("name") != want:
            same_path["name"] = want
        same_path["type"] = wiki_type
        _backfill_ids(data)                         # mọi entry thiếu id đều được gán
        save(data)
        return str(same_path["name"])

    final = want
    taken = {w.get("name") for w in wikis}
    if final in taken:                              # tên đã bị wiki khác chiếm
        final = f"{want}-{uuid.uuid4().hex[:8]}"
    wikis.append({
        "name": final,
        "id": new_id(),
        "path": target,
        "type": wiki_type,
        "added": datetime.now().isoformat(timespec="seconds"),
    })
    _backfill_ids(data)
    save(data)
    return final


def remove_wiki(name: str) -> bool:
    """Xóa wiki khỏi registry theo name HOẶC id. Trả True nếu đã xóa."""
    data = load()
    before = len(data["wikis"])
    data["wikis"] = [w for w in data["wikis"]
                     if w.get("name") != name and w.get("id") != name]
    if len(data["wikis"]) != before:
        save(data)
        return True
    return False


def get_wiki(name: str) -> dict | None:
    """Tra wiki theo name. Trả dict {name, id, path, type, added} hoặc None."""
    for w in load()["wikis"]:
        if w.get("name") == name:
            return dict(w)
    return None


def find(name_or_id: str) -> dict | None:
    """Tra theo name TRƯỚC rồi mới id — để `wiki=` chấp nhận cả hai.

    Name được ưu tiên: nếu ai đó đặt tên wiki trùng với một id hex (rất khó nhưng
    có thể), hành vi mong đợi là lấy cái có `name` đúng như vậy.
    """
    wikis = load()["wikis"]
    for key in ("name", "id"):
        for w in wikis:
            if w.get(key) == name_or_id:
                return dict(w)
    return None


def list_wikis() -> list[dict]:
    """Liệt kê tất cả wikis trong registry."""
    return [dict(w) for w in load()["wikis"]]
