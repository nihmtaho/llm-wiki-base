"""Verify workflow — set/clear `verified` trong frontmatter wiki page.

Human duyệt artifact = set `verified: {by: "human:<id>", at: <ISO-8601>}` →
trust tier *human-reviewed*. Cùng một cơ chế cho personal + project wiki
(mỗi wiki chỉ khác `--root`). Không LLM — deterministic frontmatter edit.
"""
import re
from datetime import datetime
from pathlib import Path

_FM_CLOSE_RE = re.compile(r"^---\s*$")
_VERIFIED_KEY_RE = re.compile(r"^verified\s*:")


def _resolve_page(wiki_root: Path, page: str) -> Path:
    p = Path(page)
    root = Path(wiki_root).resolve()
    full = (p if p.is_absolute() else root / p).resolve()
    if root not in full.parents and full != root:
        raise ValueError(f"path ngoài wiki root: {page}")
    if not full.exists():
        raise FileNotFoundError(f"page không tồn tại: {full}")
    return full


def _edit_verified(text: str, verified_line: str | None) -> str:
    """Set (verified_line != None) hoặc xoá (None) field `verified` trong frontmatter.

    Xoá cả block form:
        verified:
          by: ...
          at: ...
    lẫn inline form: `verified: {by: "...", at: "..."}`.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("page không có frontmatter")
    close = None
    for i in range(1, len(lines)):
        if _FM_CLOSE_RE.match(lines[i]):
            close = i
            break
    if close is None:
        raise ValueError("frontmatter không đóng (thiếu --- kết)")

    out: list[str] = []
    skipping = False
    for line in lines[1:close]:
        if _VERIFIED_KEY_RE.match(line):
            skipping = True
            continue
        if skipping:
            if line.startswith((" ", "\t")):
                continue  # block continuation (by:/at:)
            skipping = False
        out.append(line)
    if verified_line is not None:
        out.append(verified_line)
    return "---\n" + "\n".join(out) + "\n---\n" + "\n".join(lines[close + 1 :])


def set_verified(wiki_root: Path, page: str, by: str, at: str | None = None) -> Path:
    """Set `verified: {by: "human:<id>", at: <ISO-8601>}` vào frontmatter page."""
    full = _resolve_page(wiki_root, page)
    text = full.read_text(encoding="utf-8")
    human_id = by if by.startswith("human:") else f"human:{by}"
    stamp = at or datetime.now().astimezone().isoformat(timespec="seconds")
    line = 'verified: {by: "' + human_id + '", at: "' + stamp + '"}'
    full.write_text(_edit_verified(text, line), encoding="utf-8")
    return full


def unverify(wiki_root: Path, page: str) -> Path:
    """Xoá field `verified` (hạ page về unverified, chờ human duyệt lại)."""
    full = _resolve_page(wiki_root, page)
    text = full.read_text(encoding="utf-8")
    full.write_text(_edit_verified(text, None), encoding="utf-8")
    return full
