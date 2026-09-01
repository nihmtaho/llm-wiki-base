import os
import re
import sys

import db

_URL_RE = re.compile(r"^https?://")
# Chỉ flag local path cho raw/inbox/ (staging, không stable để cite).
# raw/ (ngoài inbox) là local cache do user quản lý, có thể commit + cite.
_LOCAL_RE = re.compile(r"^raw/inbox/.+\.md$", re.IGNORECASE)


def _check_sources_local_path(path: str, txt: str) -> list[str]:
    """Rule `sources-no-local-path`: frontmatter sources: KHÔNG được chứa
    `raw/inbox/...` path. Inbox là staging, file có thể move/rename → drift.

    raw/ (ngoài inbox) là local cache do user quản lý — cho phép cite.
    Nếu có inbox local path → drop, đặt `[]` (no-URL case) hoặc chỉ giữ URL.
    Trả list detail message (rỗng = pass).
    """
    m = re.search(r"^sources:\s*(\[[^\]]*\])", txt, re.MULTILINE)
    if not m:
        return []
    inner = m.group(1)
    items = [s.strip().strip('"').strip("'") for s in inner[1:-1].split(",") if s.strip()]
    bad = [s for s in items if _LOCAL_RE.match(s)]
    if bad:
        return [
            f"sources: chứa local path: {bad} — bỏ path, đặt `[]` "
            f"(xem _schema.md rule 4)"
        ]
    return []


def _check_body_inline_local_refs(path: str, txt: str) -> list[str]:
    """Rule `body-no-raw-inbox-wikilink`: body không được có `[[raw/inbox/...]]`.

    `[[raw/...]]` (ngoài inbox) được phép — user tự quyết commit/cache.
    Link local chỉ trong frontmatter sources: field (cho raw/inbox/).

    Bỏ qua match nằm trong code span (backticks) — vd: log entry mô tả rule.
    """
    # Tính range của code spans (single-backtick) và code blocks (```).
    skip_ranges: list[tuple[int, int]] = []
    # Code block ```
    for m in re.finditer(r"```[^\n]*\n.*?```", txt, re.DOTALL):
        skip_ranges.append((m.start(), m.end()))
    # Code span ` (avoid matching across ``` block — đã bỏ ở trên)
    for m in re.finditer(r"`[^`\n]+`", txt):
        if not any(s <= m.start() < e for s, e in skip_ranges):
            skip_ranges.append((m.start(), m.end()))

    def _in_skip(pos: int) -> bool:
        return any(s <= pos < e for s, e in skip_ranges)

    msgs = []
    # Chỉ flag raw/inbox/ (staging). raw/ (ngoài inbox) cho phép.
    for m in re.finditer(r"\[\[raw/inbox/[^\]]+\]\]", txt):
        if _in_skip(m.start()):
            continue
        line_no = txt[: m.start()].count("\n") + 1
        msgs.append(
            f"line {line_no}: inline `[[raw/inbox/...]]` trong body — "
            f"chuyển vào `sources:` hoặc xoá"
        )
    return msgs


def lint(conn) -> dict:
    """Health-check: orphan pages, broken [[wikilinks]], missing files.

    Critical issues (missing_file) indicate DB rows trỏ file không tồn tại —
    search trả row này nhưng file gone → broken result cho user.
    """
    WIKI_ROOT = db.WIKI_ROOT
    pages = db.list_pages(conn)
    linked = set()
    orphan = []
    missing_file = []
    findings: dict[str, list[str]] = {}  # path → [msgs]
    for p in pages:
        # Chỉ lint file trong wiki/. raw/ và archived/ là intermediate,
        # không tuân theo wiki schema (sources: rule, wikilink format).
        if not p["path"].startswith("wiki/"):
            continue
        full = os.path.join(WIKI_ROOT, p["path"])
        if not os.path.exists(full):
            missing_file.append(p["path"])
            continue
        with open(full, encoding="utf-8") as f:
            txt = f.read()
        for m in re.findall(r"\[\[([^\]]+)\]\]", txt):
            target = m.split("|")[0].strip()
            if not target.endswith(".md"):
                target += ".md"
            linked.add(os.path.normpath(target))
        msgs: list[str] = []
        msgs.extend(_check_sources_local_path(p["path"], txt))
        msgs.extend(_check_body_inline_local_refs(p["path"], txt))
        if msgs:
            findings[p["path"]] = msgs
    for p in pages:
        if not p["path"].startswith("wiki/"):
            continue
        if p["path"] == "wiki/index.md":
            continue
        if os.path.normpath(p["path"]) not in linked:
            orphan.append(p["path"])
    return {
        "page_count": len(pages),
        "orphans": orphan,
        "missing_file": missing_file,
        "findings": findings,
        "critical_count": len(missing_file),
        "note": "Contradiction là report cho human, không materialize thành edge.",
    }


def fix_missing_files(conn) -> list[str]:
    """Xóa rows trong `pages` có path không tồn tại trên disk. Trả list path đã xóa."""
    WIKI_ROOT = db.WIKI_ROOT
    pages = db.list_pages(conn)
    deleted = []
    for p in pages:
        full = os.path.join(WIKI_ROOT, p["path"])
        if not os.path.exists(full):
            conn.execute("DELETE FROM pages WHERE path = ?", (p["path"],))
            deleted.append(p["path"])
    conn.commit()
    conn.execute("DELETE FROM pages_fts WHERE rowid NOT IN (SELECT id FROM pages)")
    conn.commit()
    return deleted


if __name__ == "__main__":
    conn = db.get_conn()
    db.init_db(conn)
    if "--fix" in sys.argv:
        deleted = fix_missing_files(conn)
        if deleted:
            print(f"deleted {len(deleted)} dangling rows:")
            for p in deleted:
                print(f"  - {p}")
        else:
            print("no dangling rows to delete")
        sys.exit(0)
    result = lint(conn)
    print(f"page_count: {result['page_count']}")
    print(f"orphans: {len(result['orphans'])}")
    print(f"missing_file (CRITICAL): {len(result['missing_file'])}")
    if result["missing_file"]:
        for p in result["missing_file"]:
            print(f"  - {p}")
    if result["orphans"]:
        for p in result["orphans"]:
            print(f"  o {p}")
    findings = result.get("findings", {})
    if findings:
        print(f"\nfindings: {len(findings)} page(s) có rule violation")
        for path, msgs in findings.items():
            print(f"  ! {path}")
            for m in msgs:
                print(f"    - {m}")
    if result["critical_count"] > 0:
        print(
            f"\n{result['critical_count']} critical issue(s) — run `python tools/lint.py --fix` to delete dangling rows"
        )
        sys.exit(1)