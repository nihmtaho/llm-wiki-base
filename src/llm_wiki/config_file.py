"""Read/write `.llm-wiki.toml` ở wiki root.

Format:
    [translate]
    enabled = true
    langs = ["vi", "ja"]

Default nếu file không tồn tại: enabled=False, langs=[] → ingest không tự dịch.
"""
from pathlib import Path
from typing import Iterable

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

CONFIG_FILE = ".llm-wiki.toml"


def load(wiki_root: Path) -> dict:
    """Load `.llm-wiki.toml`. Trả dict rỗng nếu file không tồn tại."""
    p = wiki_root / CONFIG_FILE
    if not p.exists():
        return {}
    with p.open("rb") as f:
        return tomllib.load(f)


def get_translate_config(wiki_root: Path) -> tuple[bool, list[str]]:
    """Trả (enabled, langs). Default (False, [])."""
    data = load(wiki_root)
    section = data.get("translate", {})
    enabled = bool(section.get("enabled", False))
    langs = list(section.get("langs", []))
    return enabled, langs


def set_translate(wiki_root: Path, enabled: bool, langs: Iterable[str]) -> Path:
    """Ghi `.llm-wiki.toml` với `[translate]` section. Giữ các section khác nguyên.

    Returns path tới file đã ghi.
    """
    p = wiki_root / CONFIG_FILE
    data = load(wiki_root)
    data["translate"] = {
        "enabled": enabled,
        "langs": sorted(set(langs)),
    }
    _write_toml(p, data)
    return p


def _write_toml(p: Path, data: dict) -> None:
    """Manual TOML writer (stdlib chỉ có tomllib reader từ 3.11; nếu 3.10 dùng tomli cũng chỉ read).

    Hỗ trợ: section header + flat key-value (string, bool, list of string).
    Không hỗ trợ: nested tables, multiline string, datetime, integer/float (cast thành string).
    """
    lines: list[str] = []
    for section, content in data.items():
        lines.append(f"[{section}]")
        for k, v in content.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, list):
                # Quote mỗi item; chỉ support list[str] cho schema này
                quoted = ", ".join(f'"{x}"' for x in v)
                lines.append(f"{k} = [{quoted}]")
            elif isinstance(v, str):
                # Use double quotes, escape backslash + double quote
                esc = v.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{k} = "{esc}"')
            else:
                # Fallback: stringify
                lines.append(f'{k} = "{v}"')
        lines.append("")
    p.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
