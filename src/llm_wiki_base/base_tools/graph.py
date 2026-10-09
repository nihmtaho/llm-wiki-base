"""graph.py — pure, deterministic typed-relation link extraction.

Trích xuất liên kết có kiểu (typed relations) từ một page markdown:
- frontmatter `relations:` (list of dicts: rel/target/note/source)
- inline typed wikilink `[[path|rel:<rel>|<note>]]`
- plain wikilink `[[path]]` / `[[path|alias]]` → DEFAULT_REL
- bỏ qua code fence ``` và inline code span ` (cùng ngữ nghĩa lint)

Không I/O, không LLM — chỉ regex + parse frontmatter (tái dùng db).
Extraction KHÔNG đọc langpack (pack-free, không đổi hành vi wiki không pack);
I/O duy nhất là `load_langpack` — hook opt-in đọc `[langpack]` từ toml wiki
(được caller (lint/skill) chủ động gọi) → `validate_links` kiểm tra theo pack.

Interfaces (Task 2+ rely on exact names): Link, extract_links,
RESERVED_REL_PREFIX, DEFAULT_REL, load_langpack, validate_links.
"""
import os
import re
from dataclasses import dataclass

import db
from config_file import get_config

# Tương đương lint._WIKILINK_RE / lint._FM_RE — khai báo lại cục bộ để
# graph.py chỉ phụ thuộc db + config_file (flat import như lint/eval).
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FOOTNOTE_REF_RE = re.compile(r"\[\^([A-Za-z0-9_-]+)\]")
_URL_RE = re.compile(r"^https?://")

RESERVED_REL_PREFIX = "rel:"
DEFAULT_REL = "related"

# Core relation vocabulary — LUÔN hợp lệ kể cả khi wiki bật langpack, vì ý nghĩa
# độc lập ngôn ngữ: 'related' = default wikilink edge, 'contradicts' = claim-vs-claim
# (spec §5.3 — schema-notes của pack dạy `rel:contradicts`). Pack vocabulary là
# UNION thêm, không thay core.
CORE_RELS = frozenset({"related", "contradicts"})

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
    """Chuẩn hóa target về path form; giữ nguyên URL + #anchor.

    Path (non-URL) không có suffix `.md` → thêm vào — mirror lint.py
    existence-check normalization — để `[[wiki/x]]` (plain) và typed target
    `wiki/x.md` cho CÙNG dst `wiki/x.md` (không fragment graph theo form viết).
    URL và pure-anchor `#...` giữ nguyên.
    """
    dst = target.strip()
    while dst.startswith("./"):
        dst = dst[2:]
    if not dst or dst.startswith("#") or _URL_RE.match(dst):
        return dst
    path, sep, anchor = dst.partition("#")
    if path and not path.endswith(".md"):
        path += ".md"
    return path + sep + anchor


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


# ─────────────────────────────────────────────────────────────────────────────
# Language pack — opt-in `[langpack]` trong .llm-wiki-base.toml (Task 4)
# ─────────────────────────────────────────────────────────────────────────────


def _langpack_candidates(pack: str) -> list[str]:
    """Nơi tìm `templates/langpacks/<pack>/` — cùng cơ chế
    eval._template_candidates (package dir trước, global base sau):
    - `dirname(dirname(graph.__file__))` = package root (`src/llm_wiki_base/`
      khi chạy từ source, `~/.llm-wiki-base/` khi deploy tools/);
    - `LLM_WIKI_BASE_DIR`/`~/.llm-wiki-base` = global base (deployed).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.environ.get("LLM_WIKI_BASE_DIR") or os.path.expanduser(
        "~/.llm-wiki-base")
    rel = os.path.join("templates", "langpacks", pack)
    return list(dict.fromkeys([
        os.path.join(os.path.dirname(here), rel),   # package dir (src layout)
        os.path.join(base_dir, rel),                # global base (deployed)
    ]))


def load_langpack(wiki_root) -> dict | None:
    """Đọc `[langpack]` từ toml của wiki → pack dict, hoặc None nếu không bật.

    - `enabled` falsy hoặc `pack` rỗng → None — wiki không pack giữ nguyên
      hành vi (không validate gì cả).
    - Bật → load `kinds.yml` + `relations.yml` từ templates/langpacks/<pack>/
      (PyYAML `safe_load`, import LƯỜI để extraction path không phụ thuộc yaml).
    - Bật mà không tìm thấy pack → FileNotFoundError (fail loud — fail-open
      là fail thầm lặng).

    Returns: {'kinds': {...}, 'relations': {...}, 'name': pack} | None
    """
    section = get_config(wiki_root).get("langpack") or {}
    if not section.get("enabled"):
        return None
    pack = str(section.get("pack") or "").strip()
    if not pack:
        return None
    # Guard path traversal cơ bản: pack là MỘT thư mục con của langpacks/.
    if pack != os.path.basename(pack) or pack in (".", ".."):
        raise ValueError(f"tên pack không hợp lệ: {pack!r} (vd 'japanese')")
    candidates = _langpack_candidates(pack)
    directory = next(
        (p for p in candidates
         if os.path.isfile(os.path.join(p, "kinds.yml"))
         and os.path.isfile(os.path.join(p, "relations.yml"))),
        None,
    )
    if directory is None:
        raise FileNotFoundError(
            f"langpack {pack!r} không tìm thấy — tried: {', '.join(candidates)}"
            f" (chạy `llm-wiki-base setup tools` để sync templates?)")
    import yaml  # lười — chỉ khi pack bật; PyYAML có trong cả 2 venv

    def _load_doc(name: str) -> dict:
        with open(os.path.join(directory, name), encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    kinds_doc = _load_doc("kinds.yml")
    relations_doc = _load_doc("relations.yml")
    return {
        "kinds": kinds_doc.get("kinds") or {},
        "relations": relations_doc.get("relations") or {},
        "name": pack,
    }


def validate_links(links: list[Link], pack: dict | None) -> list[str]:
    """Kiểm tra link theo langpack. Trả list error strings (rỗng = hợp lệ).

    - pack=None → [] LUÔN: wiki không langpack không bị validate (zero
      behavior change — parser bỏ qua pack entirely).
    - `unknown-rel-type`: rel không có trong CORE_RELS lẫn pack['relations'].
      CORE_RELS ('related', 'contradicts') LUÔN hợp lệ — kể cả khi pack không
      khai entry riêng (union core + pack, không phải pack-only).
    - `relation-target-kind`: rel có ràng buộc `targets: [...]` mà dst không
      nằm trong kind path tương ứng (vd covered-in → dst phải qua `source/`).
    """
    if pack is None:
        return []
    rels = pack.get("relations") or {}
    name = pack.get("name") or "?"
    errors: list[str] = []
    for link in links:
        rel = link.rel
        if rel not in CORE_RELS and rel not in rels:
            errors.append(
                f"unknown-rel-type: rel {rel!r} không có trong langpack "
                f"{name!r} (dst {link.dst})")
            continue
        spec = rels.get(rel)
        if not isinstance(spec, dict):
            continue
        targets = spec.get("targets")
        if isinstance(targets, str):
            targets = [targets]
        if not targets:
            continue
        dst = "/" + link.dst.split("#", 1)[0]
        if not any(f"/{str(t).strip('/')}/" in dst for t in targets):
            allowed = ", ".join(str(t) for t in targets)
            errors.append(
                f"relation-target-kind: rel {rel!r} chỉ nhận target kind "
                f"[{allowed}] (dst {link.dst})")
    return errors
