"""graph.py — pure, deterministic typed-relation link extraction.

Trích xuất liên kết có kiểu (typed relations) từ một page markdown:
- frontmatter `relations:` (list of dicts: rel/target/note/source)
- inline typed wikilink `[[path|rel:<rel>|<note>]]`
- plain wikilink `[[path]]` / `[[path|alias]]` → DEFAULT_REL
- bỏ qua code fence ``` và inline code span ` (cùng ngữ nghĩa lint)

Không I/O, không LLM — chỉ regex + parse frontmatter (tái dùng db).
Interfaces (Task 2+ rely on exact names): Link, extract_links,
RESERVED_REL_PREFIX, DEFAULT_REL.
"""
import re
from dataclasses import dataclass

import db

# Tương đương lint._WIKILINK_RE / lint._FM_RE — khai báo lại cục bộ để
# graph.py chỉ phụ thuộc db (flat import như lint.py).
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FOOTNOTE_REF_RE = re.compile(r"\[\^([A-Za-z0-9_-]+)\]")

RESERVED_REL_PREFIX = "rel:"
DEFAULT_REL = "related"

# Priority dedup: frontmatter > inline > wikilink (số nhỏ hơn thắng).
_ORIGIN_PRIORITY = {"frontmatter": 0, "inline": 1, "wikilink": 2}


def _code_skip_ranges(txt: str) -> list[tuple[int, int]]:
    """Range code fence ``` và inline code span ` — link trong này bị bỏ qua.

    Tái hiện ngữ nghĩa lint._code_skip_ranges (graph không import lint để
    giữ dependency nhẹ) — để graph và lint đồng nhất trên cùng file.
    """
    skip: list[tuple[int, int]] = []
    for m in re.finditer(r"```[^\n]*\n.*?```", txt, re.DOTALL):
        skip.append((m.start(), m.end()))
    for m in re.finditer(r"`[^`\n]+`", txt):
        if not any(s <= m.start() < e for s, e in skip):
            skip.append((m.start(), m.end()))
    return skip


@dataclass
class Link:
    rel: str
    dst: str
    note: str | None = None
    src_footnote: str | None = None
    origin: str = "wikilink"


def _normalize_dst(target: str) -> str:
    """Chuẩn hóa target về path form; giữ nguyên #anchor."""
    dst = target.strip()
    while dst.startswith("./"):
        dst = dst[2:]
    return dst


def _strip_footnotes(text: str) -> str:
    return _FOOTNOTE_REF_RE.sub("", text)


def _frontmatter_links(fm: dict) -> list[Link]:
    """Đọc key `relations:` (list dict rel/target/note/source) từ frontmatter."""
    out: list[Link] = []
    relations = fm.get("relations")
    if not isinstance(relations, list):
        return out
    for item in relations:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("rel") or "").strip()
        target = _normalize_dst(str(item.get("target") or ""))
        if not rel or not target:
            continue
        note = item.get("note")
        source = item.get("source")
        out.append(Link(
            rel=rel,
            dst=target,
            note=str(note) if note is not None else None,
            src_footnote=str(source) if source is not None else None,
            origin="frontmatter",
        ))
    return out


def extract_links(txt: str) -> list[Link]:
    """Trích toàn bộ Link từ markdown txt. Pure, không I/O.

    - dst chuẩn hóa path form, có thể mang #anchor.
    - Dedup theo key (rel, dst) — origin frontmatter thắng inline/wikilink.
    - Trong section `## Claims`: link typed rel `contradicts` lấy note từ
      bullet sở hữu (text sau dấu `- `, bỏ footnote markers + wikilink).
    - Bỏ qua code fence ``` (cả dòng) và inline code span ` — không trích
      link, không tính bullet, đồng nhất với lint.
    """
    fm = db.parse_frontmatter(txt)
    links: list[Link] = _frontmatter_links(fm)

    m = _FM_RE.match(txt)
    body = txt[m.end():] if m else txt

    # Code fence ``` + inline span ` — không trích link, không tính bullet.
    skip = _code_skip_ranges(body)
    in_claims = False
    current_bullet: str | None = None
    pos = 0
    for raw_line in body.splitlines(keepends=True):
        line_start = pos
        pos += len(raw_line)
        line = raw_line.rstrip("\r\n")
        # Fence phủ đầu dòng → bỏ cả dòng (bullet trong fence không
        # contribute, link trong fence không trích).
        if any(s <= line_start < e for s, e in skip):
            continue
        if re.match(r"^## Claims(?:\s|$)", line):
            in_claims = True
            current_bullet = None
            continue
        if re.match(r"^##\s", line):  # heading H2 tiếp theo → hết section Claims
            in_claims = False
            current_bullet = None
            continue
        if line.strip().startswith("- "):
            current_bullet = line.strip()[2:].strip()

        for lm in _WIKILINK_RE.finditer(line):
            if any(s <= line_start + lm.start() < e for s, e in skip):
                continue  # link trong inline code span
            segs = [s.strip() for s in lm.group(1).split("|")]
            target = _normalize_dst(segs[0])
            if not target:
                continue
            alias = segs[1] if len(segs) > 1 else ""
            if alias.startswith(RESERVED_REL_PREFIX):
                rel = alias[len(RESERVED_REL_PREFIX):].split("|")[0].strip() or DEFAULT_REL
                note = segs[2] if len(segs) > 2 else None
                if (in_claims and rel == "contradicts" and current_bullet
                        and note is None):
                    # note = bullet sở hữu, bỏ wikilink + footnote markers.
                    note = _strip_footnotes(
                        _WIKILINK_RE.sub("", current_bullet)).strip() or None
                origin = "inline"
            else:
                rel = DEFAULT_REL
                note = alias or None
                origin = "wikilink"
            links.append(Link(rel=rel, dst=target, note=note,
                              src_footnote=None, origin=origin))

    # Dedup key (rel, dst) — frontmatter > inline > wikilink; cùng priority →
    # occurrence đầu giữ nguyên (dict giữ insertion order).
    seen: dict[tuple[str, str], Link] = {}
    for link in links:
        key = (link.rel, link.dst)
        prev = seen.get(key)
        if prev is None or _ORIGIN_PRIORITY[link.origin] < _ORIGIN_PRIORITY[prev.origin]:
            seen[key] = link
    return list(seen.values())
