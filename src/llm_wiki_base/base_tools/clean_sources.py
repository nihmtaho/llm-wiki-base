"""Clean `sources:` field trong wiki theo quy tắc mới.

Quy tắc transform (`sources:` frontmatter):
  - Nếu list vừa có URL vừa có local path (raw/inbox/archived) → BỎ local, GIỮ URL.
  - Nếu list chỉ có local path → GIỮ NGUYÊN (git-tracked = provenance cho file no-URL).
  - Nếu list rỗng / chỉ URL / chỉ wiki-link → GIỮ NGUYÊN.
  - Body inline `[[raw/...]]` / `[[archived/...]]` → XOÁ DÒNG.

Idempotent: chạy 2 lần liên tiếp phải cho "0 changes" ở lần 2.
Có --dry để xem diff trước khi apply.
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from paths import WIKI_DIR  # noqa: E402

WIKI = Path(WIKI_DIR)
URL_RE = re.compile(r"^https?://")
# Chỉ flag local path cho raw/inbox/ (staging, không stable để cite).
# raw/ (ngoài inbox) là local cache, có thể do user commit + cite.
LOCAL_RE = re.compile(r"^raw/inbox/.+\.md$", re.IGNORECASE)
SOURCES_RE = re.compile(r"^sources:\s*(.*)$", re.MULTILINE)
# Body inline: cả dòng chứa [[raw/...]] hoặc [[archived/...]]
INLINE_BODY_RE = re.compile(
    r"^.*\[\[(?:archived|raw)/[^\]]+\]\].*\n?",
    re.MULTILINE,
)


def _parse_list(value: str) -> list[str]:
    """Parse một YAML-ish list string thành list[str], strip quote."""
    inner = value.strip()
    if inner in ("[]", "[ ]"):
        return []
    if not (inner.startswith("[") and inner.endswith("]")):
        return []
    items: list[str] = []
    for s in inner[1:-1].split(","):
        s = s.strip().strip('"').strip("'")
        if s:
            items.append(s)
    return items


def _format_list(items: list[str]) -> str:
    return "[" + ", ".join(items) + "]"


def transform_sources_line(value: str) -> tuple[str, bool]:
    """Transform `sources:` value theo quy tắc. Trả (new_value, changed).

    Quy tắc hiện tại:
    - BỎ TẤT CẢ local path trong raw/inbox/ khỏi sources:.
    - raw/ (ngoài inbox) là local cache do user quản lý, có thể cite nếu user muốn.
    - Nếu còn URL sau khi bỏ → giữ URL.
    - Nếu không còn gì → sources: [] (page tự đứng, không cần provenance local).
    - Wiki cross-link `[[wiki/...]]` → giữ nguyên.
    """
    items = _parse_list(value)
    if not items:
        return value, False  # rỗng → giữ nguyên

    new_items = [s for s in items if not LOCAL_RE.match(s)]
    if new_items == items:
        return value, False  # không có local path → giữ nguyên
    if not new_items:
        return "[]", True
    return _format_list(new_items), True


def transform_file(path: Path) -> tuple[str, str, bool]:
    """Trả (old_text, new_text, changed)."""
    text = path.read_text(encoding="utf-8")
    new = text

    # 1) sources: line trong frontmatter (chỉ match line đầu tiên — frontmatter
    # convention là sources: ở đầu, trước --- đóng. Body không có `sources:` field.)
    def _repl_src(m: re.Match) -> str:
        new_val, _ = transform_sources_line(m.group(1))
        return f"sources: {new_val}"

    new = SOURCES_RE.sub(_repl_src, new, count=1)

    # 2) body inline refs
    new2 = INLINE_BODY_RE.sub("", new)

    return text, new2, new2 != text


def _print_diff(path: Path, old: str, new: str) -> None:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    import difflib

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=str(path),
        tofile=str(path),
        n=2,
    )
    for line in diff:
        sys.stdout.write(line)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean sources: field trong wiki (xoá local path khi đã có URL)."
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Chỉ in diff, không ghi file.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Không in diff từng file, chỉ in tổng kết.",
    )
    args = parser.parse_args()

    if not WIKI.is_dir():
        print(f"error: {WIKI} không tồn tại — chạy từ repo root", file=sys.stderr)
        return 1

    changed_files: list[Path] = []
    for md in sorted(WIKI.rglob("*.md")):
        old, new, changed = transform_file(md)
        if changed:
            changed_files.append(md)
            if not args.dry:
                md.write_text(new, encoding="utf-8")
            if not args.quiet and not args.dry:
                # apply mode + không quiet → in tóm tắt
                pass

    # Print report
    if args.dry:
        print(f"=== DRY RUN: {len(changed_files)} file sẽ thay đổi ===\n")
        for p in changed_files:
            old, new, _ = transform_file(p)
            _print_diff(p, old, new)
        print(f"\nTổng: {len(changed_files)} file")
    else:
        for p in changed_files:
            print(f"updated: {p}")
        print(f"\nTổng: {len(changed_files)} file đã được cập nhật.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
