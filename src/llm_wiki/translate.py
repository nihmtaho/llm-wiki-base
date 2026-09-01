"""Translation utilities: file detection + structure check + helpers.

**Translation đã chuyển sang AI-driven** — chạy qua skill `llm-wiki-translate` (dùng
LLM của AI tool đang chạy, vd Claude Code → Claude). Subcommand CLI `translate add`
đã deprecated; dùng `translate enable --lang vi` để setup target langs, rồi ingest
sẽ tự gọi skill.

File này giữ lại:
- `is_translated_file(path)` — skip rule dùng trong tools/{ingest,reindex,watch}.py + rag/index.py.
- `parse_frontmatter`, `extract_headings` — helpers cho skill.
- `run_check(wiki_root, lang)` — verify đồng bộ, KHÔNG cần LLM.
"""
import re
from pathlib import Path

from rich.console import Console

console = Console()

# Pattern: <slug>.<lang>.md (lang là 2-3 chữ cái thường). Bị skip khỏi DB/RAG ingest.
TRANSLATED_SUFFIX_RE = re.compile(r"^(?P<slug>.+)\.(?P<lang>[a-z]{2,3})\.md$")

# Lang mặc định của source (file không có suffix .lang.md) — không skip.
SOURCE_LANG_DEFAULT = "en"

# Frontmatter parser tối thiểu (đủ cho check keys + heading structure)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)


def is_translated_file(path: Path) -> bool:
    """True nếu file là bản dịch (match pattern <slug>.<lang>.md với lang != SOURCE_LANG_DEFAULT)."""
    m = TRANSLATED_SUFFIX_RE.match(path.name)
    return bool(m and m.group("lang") != SOURCE_LANG_DEFAULT)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse frontmatter YAML-like + return (dict, body). Empty dict nếu không có."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    block = m.group(1)
    meta: dict = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip()
    return meta, text[m.end():]


def extract_headings(text: str) -> list[str]:
    """Trả list heading lines (bao gồm leading #), giữ nguyên để so sánh structure."""
    return _HEADING_RE.findall(text)


def detect_translated_files(wiki_dir: Path) -> set[Path]:
    """Trả set path (relative to wiki_dir) của file *.lang.md (translated)."""
    out: set[Path] = set()
    for f in wiki_dir.rglob("*.md"):
        if is_translated_file(f):
            out.add(f.relative_to(wiki_dir))
    return out


def run_check(wiki_root: Path, lang: str) -> int:
    """Verify mỗi foo.md có foo.<lang>.md với cùng frontmatter keys + heading structure.

    Không cần LLM — chỉ đọc file + so sánh structure. Return 0 nếu pass, 1 nếu có issue.
    """
    wiki_dir = wiki_root / "wiki"
    issues: list[str] = []

    for src in sorted(wiki_dir.rglob("*.md")):
        if is_translated_file(src):
            continue
        tgt = src.with_suffix(f".{lang}.md")
        if not tgt.exists():
            issues.append(f"missing translation: {tgt.relative_to(wiki_root)}")
            continue
        # Compare frontmatter keys
        sm, _ = parse_frontmatter(src.read_text(encoding="utf-8"))
        tm, _ = parse_frontmatter(tgt.read_text(encoding="utf-8"))
        if set(sm.keys()) != set(tm.keys()):
            issues.append(
                f"frontmatter keys mismatch: {tgt.relative_to(wiki_root)} "
                f"(src: {sorted(sm.keys())}, tgt: {sorted(tm.keys())})"
            )
        # Compare heading structure (count + levels + text, không so sánh anchor ID)
        sh = extract_headings(src.read_text(encoding="utf-8"))
        th = extract_headings(tgt.read_text(encoding="utf-8"))
        if sh != th:
            issues.append(f"heading structure mismatch: {tgt.relative_to(wiki_root)}")

    if issues:
        console.print(f"[red]{len(issues)} issues found:[/red]")
        for i in issues:
            console.print(f"  - {i}")
        return 1
    console.print(f"[green]✓ All pages in lang='{lang}' are in sync.[/green]")
    return 0
