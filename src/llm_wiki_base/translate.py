"""Translation layout: detection + structure check + legacy migration.

**Translation đã chuyển sang AI-driven** — chạy qua skill `llm-wiki-base-translate` (dùng
LLM của AI tool đang chạy, vd Claude Code → Claude). CLI `translate enable --lang vi`
chỉ setup target langs; skill tạo file.

Layout (v0.2+): bản dịch nằm trong cây SONG SONG `wiki-<lang>/`, mirror `wiki/` từng path:

    wiki/<domain>/<kind>/<slug>.md          →  wiki-<lang>/<domain>/<kind>/<slug>.md

Vì `wiki-<lang>/` là sibling của `wiki/` (không nằm trong), indexer (BM25/RAG chạy trên
`wiki/` + `raw/`) tự bỏ qua — không cần skip rule runtime. File cũ dạng `<slug>.<lang>.md`
(legacy, nằm lẫn trong `wiki/`) vẫn được nhận diện để không lọt index, và move được
bằng `translate migrate`.

Module này giữ:
- `run_check(wiki_root, lang)` — verify mirror, KHÔNG cần LLM.
- `migrate_translations(wiki_root, lang)` — move layout cũ → `wiki-<lang>/`.
- `parse_frontmatter`, `extract_headings` — helpers cho skill.
"""
import re
import shutil
from pathlib import Path

from rich.console import Console

console = Console()

# Lang gốc của wiki (file không suffix) — không coi là bản dịch.
SOURCE_LANG_DEFAULT = "en"

# Layout cũ: `<slug>.<lang>.md` — `<lang>` 2-3 chữ thường.
TRANSLATED_SUFFIX_RE = re.compile(r"^(?P<slug>.+)\.(?P<lang>[a-z]{2,3})\.md$")

_LANG_RE = re.compile(r"^[a-z]{2,3}$")

# Frontmatter parser tối thiểu (đủ cho check keys + heading structure)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)


def translation_dir_name(lang: str) -> str:
    """Tên thư mục dịch cho 1 lang, vd 'vi' → 'wiki-vi'. Raise nếu lang sai định dạng."""
    if not _LANG_RE.match(lang or ""):
        raise ValueError(f"lang không hợp lệ: {lang!r} (cần 2-3 chữ thường, vd 'vi')")
    return f"wiki-{lang}"


def _legacy_translated(name: str) -> bool:
    """True nếu filename là `<slug>.<lang>.md` với lang != SOURCE_LANG_DEFAULT."""
    m = TRANSLATED_SUFFIX_RE.match(name)
    return bool(m and m.group("lang") != SOURCE_LANG_DEFAULT)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse frontmatter YAML-like + return (dict, body). Empty dict nếu không có."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip()
    return meta, text[m.end():]


def extract_headings(text: str) -> list[str]:
    """Trả list heading lines (bao gồm leading #), giữ nguyên để so sánh structure."""
    return _HEADING_RE.findall(text)


def _skip_rel(rel: Path) -> bool:
    """File hạ tầng / ẩn trong cây wiki: không dịch, không coi là content page.

    `log.md` là lịch sử append-only (không dịch). `index.md` được phép dịch (mirror đầy đủ).
    """
    if any(part.startswith(".") for part in rel.parts):
        return True
    return rel.name.lower() == "log.md"


def run_check(wiki_root: Path, lang: str) -> int:
    """Verify cây `wiki-<lang>/` mirror `wiki/`: đủ file, cùng frontmatter keys + heading structure.

    Không cần LLM — chỉ đọc file + so sánh structure. Return 0 nếu pass, 1 nếu có issue.
    """
    wiki_root = Path(wiki_root)
    src_dir = wiki_root / "wiki"
    tgt_dir = wiki_root / translation_dir_name(lang)
    if not src_dir.is_dir():
        console.print(f"[red]không có {src_dir}[/red]")
        return 1

    issues: list[str] = []
    seen: set[Path] = set()

    for src in sorted(src_dir.rglob("*.md")):
        rel = src.relative_to(src_dir)
        if _skip_rel(rel) or _legacy_translated(src.name):
            continue
        seen.add(rel)
        tgt = tgt_dir / rel
        if not tgt.exists():
            issues.append(f"missing translation: {tgt.relative_to(wiki_root)}")
            continue
        src_txt = src.read_text(encoding="utf-8")
        tgt_txt = tgt.read_text(encoding="utf-8")
        sm, _ = parse_frontmatter(src_txt)
        tm, _ = parse_frontmatter(tgt_txt)
        if set(sm.keys()) != set(tm.keys()):
            issues.append(
                f"frontmatter keys mismatch: {tgt.relative_to(wiki_root)} "
                f"(src: {sorted(sm.keys())}, tgt: {sorted(tm.keys())})"
            )
        if extract_headings(src_txt) != extract_headings(tgt_txt):
            issues.append(f"heading structure mismatch: {tgt.relative_to(wiki_root)}")

    # File mồ côi trong cây dịch (source đã xoá/đổi tên) — báo, không tự xoá.
    if tgt_dir.is_dir():
        for tgt in sorted(tgt_dir.rglob("*.md")):
            rel = tgt.relative_to(tgt_dir)
            if _skip_rel(rel) or _legacy_translated(tgt.name) or rel in seen:
                continue
            issues.append(f"orphan translation (no source): {tgt.relative_to(wiki_root)}")

    if issues:
        console.print(f"[red]{len(issues)} issues found:[/red]")
        for i in issues:
            console.print(f"  - {i}")
        return 1
    console.print(f"[green]✓ All pages in lang='{lang}' are in sync.[/green]")
    return 0


def migrate_translations(wiki_root: Path, lang: str) -> list[tuple[str, str]]:
    """Move file legacy `wiki/**/<slug>.<lang>.md` → `wiki-<lang>/**/<slug>.md`.

    Additive + an toàn: file đích đã tồn tại → giữ nguồn, KHÔNG ghi đè.
    Trả list (src_rel, dst_rel) đã move (rỗng nếu không có gì).
    """
    wiki_root = Path(wiki_root)
    wiki_dir = wiki_root / "wiki"
    tgt_root = wiki_root / translation_dir_name(lang)
    suffix = f".{lang}.md"
    moved: list[tuple[str, str]] = []
    if not wiki_dir.is_dir():
        return moved
    for src in sorted(wiki_dir.rglob(f"*{suffix}")):
        rel = src.relative_to(wiki_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        new_rel = rel.with_name(rel.name[: -len(suffix)] + ".md")
        dst = tgt_root / new_rel
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved.append(
            (src.relative_to(wiki_root).as_posix(), dst.relative_to(wiki_root).as_posix())
        )
    return moved
