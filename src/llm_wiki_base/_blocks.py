"""Comment-preserving edits to TOML / YAML config files.

`installer.py` merges one MCP server entry into a client's config file. For JSON
that is a load → merge → dump round-trip. For TOML (`~/.codex/config.toml`) and
YAML (`~/.hermes/config.yaml`) a round-trip is NOT acceptable: those files are
hand-maintained and full of their owner's comments, which `tomli_w.dump` (or any
YAML dumper) would silently erase. Same rule `config_file.py` already follows for
`.llm-wiki-base.toml`.

So this module edits them as TEXT inside a delimited managed block:

    # BEGIN llm-wiki-base (managed by `llm-wiki-base setup`; server=<name>)
    [mcp_servers.<name>]
    command = "llm-wiki-base"
    args = ["serve", "--mcp"]
    # END llm-wiki-base

What keeps the result valid:

* `upsert()` removes the block for that one server name and re-inserts it —
  replacing our own block is how idempotency works, and nothing outside the
  markers moves.
* A YAML entry goes INSIDE the file's existing `mcp_servers:` mapping when there
  is one (a second top-level key would be a duplicate), at the indentation the
  file already uses.
* `validate()` parses the result before it is written, so a file we would corrupt
  is refused rather than broken.
* `drop()` also removes hand-written entries — installed by an older version, or
  pasted by the human from a snippet we printed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover - py3.10
    import tomli as tomllib  # type: ignore

#: Marker prefix. Wording after it may change; the name is the contract.
BLOCK_BEGIN = "# BEGIN llm-wiki-base"
BLOCK_END = "# END llm-wiki-base"

#: Fields of an entry, in the order we print them.
ENTRY_FIELDS = ("type", "transport", "command", "args", "cwd", "enabled")


def _begin_line(name: str) -> str:
    return f"{BLOCK_BEGIN} (managed by `llm-wiki-base setup`; server={name})"


def _block_re(name: str | None) -> re.Pattern[str]:
    """The managed block for one server name, or for any name when `name` is None.

    The optional leading blank line is the separator `upsert` inserts, so
    removing a block does not leave a pile of empty lines behind.
    """
    who = re.escape(name) if name else r"[^\s)]+"
    return re.compile(
        rf"(?:^[ \t]*\n)?^[ \t]*{re.escape(BLOCK_BEGIN)}[^\n]*\bserver={who}\b[^\n]*\n"
        rf".*?"
        rf"^[ \t]*{re.escape(BLOCK_END)}[ \t]*\n?",
        re.MULTILINE | re.DOTALL,
    )


def has_block(text: str, name: str | None = None) -> bool:
    return bool(_block_re(name).search(text))


def strip_block(text: str, name: str | None = None) -> str:
    """Remove managed block(s). Text outside them comes back byte-identical."""
    return _block_re(name).sub("", text)


def block_names(text: str) -> list[str]:
    """Server names we already manage in this file."""
    return re.findall(rf"{re.escape(BLOCK_BEGIN)}[^\n]*\bserver=([^\s)]+)", text)


# ─────────────────────────────────────────────────────────────────────────────
# rendering
# ─────────────────────────────────────────────────────────────────────────────

def _key(name: str) -> str:
    """Bare TOML/YAML key when legal (`llm-wiki-base-mcp` is), quoted otherwise."""
    return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else json.dumps(name)


def _scalar(value: object) -> str:
    """JSON serialization is valid TOML *and* valid YAML for our value types."""
    return json.dumps(value, ensure_ascii=False)


def _fields(entry: dict, indent: int, fmt: str) -> list[str]:
    pad = " " * indent
    sep = " = " if fmt == "toml" else ": "
    return [f"{pad}{f}{sep}{_scalar(entry[f])}" for f in ENTRY_FIELDS if f in entry]


def render_entry(fmt: str, key: str, name: str, entry: dict, indent: int) -> str:
    """One server entry, no markers. TOML → a table; YAML → a mapping child."""
    env = entry.get("env") or {}
    if fmt == "toml":
        path = f"{key}.{_key(name)}"
        lines = [f"[{path}]"] + _fields(entry, 0, fmt)
        if env:
            lines += ["", f"[{path}.env]"] + [f"{k} = {_scalar(v)}" for k, v in env.items()]
        return "\n".join(lines) + "\n"
    pad = " " * indent
    lines = [f"{pad}{_key(name)}:"] + _fields(entry, indent + 2, fmt)
    if env:
        lines.append(" " * (indent + 2) + "env:")
        lines += [" " * (indent + 4) + f"{k}: {_scalar(v)}" for k, v in env.items()]
    return "\n".join(lines) + "\n"


def render_block(fmt: str, key: str, name: str, entry: dict, own_header: bool = False) -> str:
    """Markers + entry. `own_header` also writes the top-level `key:` line (YAML)."""
    if own_header and fmt == "yaml":
        body = f"{key}:\n" + render_entry(fmt, key, name, entry, 2)
    else:
        body = render_entry(fmt, key, name, entry, 0)
    return f"{_begin_line(name)}\n{body}{BLOCK_END}\n"


# ─────────────────────────────────────────────────────────────────────────────
# reading
# ─────────────────────────────────────────────────────────────────────────────

def _mapping_line(key: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(key)}[ \t]*:[ \t]*(#.*)?$", re.MULTILINE)


def names(fmt: str, text: str, key: str) -> list[str]:
    """Server names present in the file — ours or the owner's."""
    if not text.strip():
        return []
    if fmt == "toml":
        return [n.strip('"') for n in
                re.findall(rf"^\[{re.escape(key)}\.([^\]\s]+)\][ \t]*$", text, re.MULTILINE)]
    return _yaml_children(text, key)


def _yaml_children(text: str, key: str) -> list[str]:
    """Child keys of a top-level YAML mapping, at whatever indentation it uses."""
    return [child["name"] for child in _yaml_child_spans(text, key)]


def _yaml_child_spans(text: str, key: str) -> list[dict]:
    """[{name, start, end}] line indexes for the children of `key:`."""
    lines = text.splitlines()
    m = _mapping_line(key).search(text)
    if not m:
        return []
    start = text[:m.start()].count("\n") + 1        # first line after `key:`
    child_indent: int | None = None
    spans: list[dict] = []
    for i in range(start, len(lines)):
        ln = lines[i]
        stripped = ln.strip()
        indent = len(ln) - len(ln.lstrip())
        if not stripped or stripped.startswith("#"):
            continue
        if indent == 0:                              # left the mapping
            break
        if child_indent is None:
            child_indent = indent
        if indent == child_indent:
            spans.append({"name": _child_name(ln), "start": i, "end": i + 1})
        elif indent > child_indent and spans:
            spans[-1]["end"] = i + 1        # deeper line: part of the previous child
    return [s for s in spans if s["name"]]


def _child_name(line: str) -> str:
    m = re.match(r"^[ \t]*([^:#]+)[ \t]*:", line)
    return m.group(1).strip().strip('"').strip("'") if m else ""


def _toml_table_re(key: str, name: str) -> re.Pattern[str]:
    """One `[key.name]` table: up to the next table header OR a managed-block
    marker. Without the marker boundary a table would swallow the `# BEGIN
    llm-wiki-base … server=…` comment that follows it and match on that text."""
    return re.compile(
        rf"^\[{re.escape(key)}\.{re.escape(_key(name))}\][ \t]*$.*?"
        rf"(?=^[ \t]*\[|^[ \t]*{re.escape(BLOCK_BEGIN)}|\Z)",
        re.MULTILINE | re.DOTALL)


def child_text(fmt: str, text: str, key: str, name: str) -> str:
    """The raw lines of one entry — enough to marker-scan without a real parser."""
    if fmt == "toml":
        m = _toml_table_re(key, name).search(text)
        return m.group(0) if m else ""
    span = next((s for s in _yaml_child_spans(text, key) if s["name"] == name), None)
    if not span:
        return ""
    return "\n".join(text.splitlines()[span["start"]:span["end"]])


def entry_of(fmt: str, text: str, key: str, name: str) -> dict | None:
    """One entry as a dict, for the "cwd changed" warning.

    None when it is not machine-readable here — notably a commented YAML file,
    which this module deliberately does not parse.
    """
    if fmt == "toml":
        try:
            doc = tomllib.loads(text)
        except Exception:
            return None
        container = doc.get(key)
        return container.get(name) if isinstance(container, dict) else None
    if fmt != "yaml":
        return None
    block = _block_re(name).search(text)
    if not block:
        return None
    found: dict[str, object] = {}
    for m in re.finditer(r"^[ \t]+([A-Za-z_]+)[ \t]*:(.+?)[ \t]*$",
                         block.group(0), re.MULTILINE):
        try:
            found[m.group(1)] = json.loads(m.group(2))
        except ValueError:
            found[m.group(1)] = m.group(2)
    return found or None


# ─────────────────────────────────────────────────────────────────────────────
# writing
# ─────────────────────────────────────────────────────────────────────────────

def _child_indent(text: str, mapping: re.Match[str]) -> int:
    """Indentation in use under an existing `key:` line (2 when it is empty)."""
    for ln in text[mapping.end():].splitlines():
        stripped = ln.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return (len(ln) - len(ln.lstrip())) or 2     # empty mapping → 2 is fine
    return 2


def upsert(fmt: str, text: str, key: str, name: str, entry: dict) -> str:
    """Insert or replace the managed block for `name`; the rest of the file is intact."""
    rest = strip_block(text, name)
    if rest and not rest.endswith("\n"):
        rest += "\n"
    if fmt == "toml":
        _refuse_inline_toml(rest, key)
        return rest + "\n" + render_block(fmt, key, name, entry)
    mapping = _mapping_line(key).search(rest)
    if mapping is None:                      # no such mapping yet → we own the header too
        return rest + "\n" + render_block(fmt, key, name, entry, own_header=True)
    indent = _child_indent(rest, mapping)
    inner = " " * indent
    block = (f"{inner}{_begin_line(name)}\n"
             + render_entry(fmt, key, name, entry, indent)
             + f"{inner}{BLOCK_END}\n")
    spans = _yaml_child_spans(rest, key)
    at = spans[-1]["end"] if spans else rest[:mapping.start()].count("\n") + 1
    lines = rest.splitlines(keepends=True)
    return "".join(lines[:at]) + block + "".join(lines[at:])


def drop(fmt: str, text: str, key: str, name: str) -> str:
    """Remove one server entry — our managed block, or a hand-written one."""
    if has_block(text, name):
        return strip_block(text, name)
    if fmt == "toml":
        return _drop_toml_table(text, key, name)
    return _drop_yaml_entry(text, key, name)


def _refuse_inline_toml(text: str, key: str) -> None:
    """`mcp_servers = { ... }` cannot be extended by a `[mcp_servers.x]` table."""
    if re.search(rf"^{re.escape(key)}[ \t]*=[ \t]*\{{", text, re.MULTILINE):
        raise ValueError(
            f"{key} đang là inline table trong file TOML này — không thêm "
            f"[{key}.<name>] vào sau nó được. Viết lại thành header "
            f"[{key}.<name>] rồi chạy lại.")


def _drop_toml_table(text: str, key: str, name: str) -> str:
    """Delete `[key.name]` (and its `.env` sub-table) up to the next boundary."""
    return _toml_table_re(key, name).sub("", text)


def _drop_yaml_entry(text: str, key: str, name: str) -> str:
    """Delete the `name:` child of the top-level `key:` mapping."""
    lines = text.splitlines(keepends=True)
    spans = _yaml_child_spans(text, key)
    kill = {s["name"] for s in spans if s["name"] == name}
    if not kill:
        return text
    drop_idx = {i for s in spans if s["name"] in kill for i in range(s["start"], s["end"])}
    return "".join(ln for i, ln in enumerate(lines) if i not in drop_idx)


def validate(fmt: str, text: str, path: Path | None = None) -> None:
    """Parse `text` the way the client would; raise ValueError with a fix hint."""
    where = str(path) if path else "config"
    if fmt == "toml":
        try:
            tomllib.loads(text)
        except Exception as e:
            raise ValueError(
                f"{where} không phải TOML hợp lệ sau khi sửa ({e}) — "
                f"llm-wiki-base KHÔNG ghi đè file hỏng") from None
        return
    if fmt == "yaml":
        _validate_yaml(where, text)
        return
    try:
        json.loads(text)
    except ValueError as e:
        raise ValueError(f"{where} không phải JSON hợp lệ sau khi sửa ({e})") from None


def _validate_yaml(where: str, text: str) -> None:
    """Deliberately no YAML parser (no new dependency) — so check the two things
    a text edit can actually break: duplicate top-level keys, and tab indentation.
    """
    counts: dict[str, int] = {}
    for ln in text.splitlines():
        if not ln.strip() or ln[0] in " \t#":
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)[ \t]*:", ln)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    dupes = sorted(k for k, n in counts.items() if n > 1)
    if dupes:
        raise ValueError(
            f"{where} sẽ có key trùng ở top-level ({', '.join(dupes)}) — "
            f"llm-wiki-base không ghi. Thêm server vào mapping có sẵn tay, hoặc "
            f"xoá block cũ của llm-wiki-base rồi chạy lại.")
    if re.search(r"^[ ]*\t", text, re.MULTILINE):
        raise ValueError(f"{where} dùng tab để indent (YAML không cho phép) — "
                         f"sửa lại rồi chạy lại")
