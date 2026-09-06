#!/usr/bin/env python3
"""Quản lý `wiki/.proposals/` — staging area cho đề xuất sửa wiki của AI.

`wiki_propose_edit` (MCP) trước đây CHỈ ghi file rồi quên: không có cách nào biết
proposal nhắm page nào (tên file chỉ giữ `basename`), không có lệnh xem/duyệt/bỏ.
Kết quả là proposal nằm mục rữa — một proposal chứa correction thật (sửa import path
sai) bị bỏ quên trong khi page vẫn giữ nội dung sai.

Module này đóng vòng hở đó:

    proposals.py list                     bảng proposal + diff size so với target
    proposals.py show   <name>            metadata + unified diff
    proposals.py apply  <name> [--by ID]  ghi vào target + log entry + (verify) + xoá
    proposals.py discard <name>            xoá, không ghi gì
    proposals.py new --target <path> --file <content-file> [--note ...]  tạo có metadata

Định dạng proposal: header comment khai metadata, phần còn lại là NỘI DUNG nguyên
văn sẽ ghi vào target. Comment dạng HTML để markdown renderer ẩn nó đi, và để
frontmatter của page được đề xuất vẫn là frontmatter thật (không phải metadata proposal).

An toàn: `apply` KHÔNG bao giờ ghi ra ngoài `wiki/` của wiki hiện tại (chuẩn hoá
path + kiểm tra tiền tố), và không tự đặt `verified` trừ khi người ra lệnh đưa
`--by <id>` — đó chính là chữ ký của họ.
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db  # noqa: E402

HEADER_RE = re.compile(
    r"^<!--\s*llm-wiki-proposal\s*\n(?P<meta>.*?)\n?-->\s*\n?", re.DOTALL)
TS_FMT = "%Y%m%d-%H%M%S"


def wiki_root() -> Path:
    return Path(os.environ.get("WIKI_ROOT") or Path.cwd()).resolve()


def proposals_dir() -> Path:
    return wiki_root() / "wiki" / ".proposals"


# ───────────────────────────────────────────────────────────── parse / format

def parse(path: Path) -> tuple[dict, str]:
    """Trả (metadata, content). Proposal cũ không có header → metadata rỗng."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = HEADER_RE.match(text)
    if not m:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group("meta").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def format_meta(meta: dict) -> str:
    lines = "\n".join(f"{k}: {v}" for k, v in meta.items() if v)
    return f"<!-- llm-wiki-proposal\n{lines}\n-->\n"


def target_path(meta: dict, name: str) -> Path | None:
    """Đường dẫn tuyệt đối của page đích, hoặc None nếu proposal cũ không khai target.

    chặn mọi thứ lọt ra ngoài `wiki/` — proposal không được phép là đường thoát
    để ghi tuỳ ý lên đĩa.
    """
    raw = meta.get("target")
    if not raw:
        return None
    root = wiki_root()
    rel = raw if not Path(raw).is_absolute() else Path(raw).resolve().relative_to(root)
    dest = (root / rel).resolve()
    try:
        dest.relative_to((root / "wiki").resolve())
    except ValueError:
        return None                       # lọt ra ngoài wiki/ → từ chối
    return dest


def guess_target(name: str) -> str:
    """Gợi ý target cho proposal CŨ (chỉ có basename trong tên file).

    CHỈ để hiển thị + xem diff. `apply` không dùng đoán này: đoán sai thì ghi đè
    nhầm page thật, nên apply bắt buộc metadata đúng hoặc `--target` tường minh.
    """
    hits = guess_targets(name)
    if len(hits) == 1:
        return hits[0]
    return f"? ({len(hits)} file khớp '{name.split('__', 1)[-1]}')" if hits else "?"


def guess_targets(name: str) -> list[str]:
    base = name.split("__", 1)[-1]
    root = wiki_root()
    return sorted(p.relative_to(root).as_posix()
                  for p in (root / "wiki").rglob(base)
                  if ".proposals" not in p.parts)


def resolve_dest(meta: dict, name: str) -> Path | None:
    """Đích để ĐẾM DIFF: metadata trước, không có thì guess duy nhất trên đĩa."""
    dest = target_path(meta, name)
    if dest is not None:
        return dest
    hits = guess_targets(name)
    return (wiki_root() / hits[0]) if len(hits) == 1 else None


def _read_target(meta: dict, name: str) -> str | None:
    """Nội dung page đích hiện tại (theo resolve_dest). None nếu chưa có file."""
    dest = resolve_dest(meta, name)
    if dest is None or not dest.exists():
        return None
    return dest.read_text(encoding="utf-8")


def listing() -> list[dict]:
    out = []
    d = proposals_dir()
    if not d.is_dir():
        return out
    for p in sorted(d.iterdir()):
        if p.name.startswith(".") or not p.is_file():
            continue
        meta, content = parse(p)
        declared = bool(meta.get("target"))
        dest = resolve_dest(meta, p.name)
        out.append({
            "name": p.name,
            "target": meta.get("target") or (guess_target(p.name) if not declared else ""),
            "declared": declared,
            "created": meta.get("created", ""),
            "lines": len(content.splitlines()),
            "found": dest is not None and dest.exists(),
            "delta": _diff_counts(content, meta, p.name),
        })
    return out


def _diff_counts(content: str, meta: dict, name: str) -> str:
    cur = _read_target(meta, name)
    if cur is None:
        return "mới (chưa có page)" if resolve_dest(meta, name) else "?"
    a, b = cur.splitlines(), content.splitlines()
    diff = [l for l in difflib.unified_diff(a, b, n=0, lineterm="")]
    plus = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    minus = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    return f"+{plus}/-{minus}"


def stage(root: Path | str, target: str, content: str,
          by: str = "", note: str = "", wiki: str = "") -> Path:
    """Ghi 1 proposal mới kèm metadata. Entry point cho MCP servers + CLI `new`.

    Tên file giữ `basename` của target (đọc được bằng mắt) nhưng thông tin thật —
    target đầy đủ, ai đề xuất, wiki nào, lúc nào — nằm trong header comment, để
    `list`/`show` không phải đoán. Trả về path file proposal.
    """
    d = Path(root) / "wiki" / ".proposals"
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime(TS_FMT)
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(target).name)
    prop = d / f"{stamp}__{safe}"
    n = 1
    while prop.exists():                       # 2 proposal cùng giây cùng file đích
        prop = d / f"{stamp}__{safe}.{n}"
        n += 1
    meta = {"target": target, "wiki": wiki,
            "created": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "by": by, "note": note}
    prop.write_text(format_meta(meta) + content, encoding="utf-8")
    return prop


# ───────────────────────────────────────────────────────────── commands

def cmd_list(_: argparse.Namespace) -> int:
    rows = listing()
    if not rows:
        print(f"Không có proposal nào trong {proposals_dir()}")
        print("Proposal được tạo bởi MCP tool `wiki_propose_edit` hoặc `llm-wiki proposals new`.")
        return 0
    print(f"{len(rows)} proposal trong {proposals_dir()}:\n")
    for r in rows:
        flag = "" if r["found"] else "   [KHÔNG tìm thấy page đích trên đĩa]"
        src = "" if r["declared"] else "   (target đoán từ tên file — apply cần --target)"
        print(f"  {r['name']}")
        print(f"    target : {r['target']}{src}")
        print(f"    tạo    : {r['created'] or '?'}   nội dung: {r['lines']} dòng   "
              f"đổi so với hiện tại: {r['delta']}{flag}")
    print()
    print("Xem diff: `llm-wiki proposals show <name>`")
    print("Duyệt   : `llm-wiki proposals apply <name> --by <human-id>`")
    print("Bỏ      : `llm-wiki proposals discard <name>`")
    return 0


def cmd_show(a: argparse.Namespace) -> int:
    p = _resolve(a.name)
    if p is None:
        return 1
    meta, content = parse(p)
    print(f"# {p.name}")
    for k in ("target", "created", "by", "note"):
        if meta.get(k):
            print(f"  {k}: {meta[k]}")
    if not meta.get("target"):
        print(f"  [!] proposal cũ không khai target — gợi ý: {guess_target(p.name)}")
        print("      apply cần: --target <path>")
    dest = resolve_dest(meta, p.name)
    cur = _read_target(meta, p.name)
    if cur is None and dest is None:
        print("\n[không xác định được page đích — cần `apply --target <path>`]\n")
        print(content)
        return 0
    if cur is None:
        print(f"\n[page đích chưa tồn tại — apply sẽ tạo mới {dest}]\n")
        print(content)
        return 0
    diff = list(difflib.unified_diff(
        cur.splitlines(), content.splitlines(),
        fromfile=f"a/{dest.relative_to(wiki_root())}",
        tofile=f"b/{dest.relative_to(wiki_root())}",
        lineterm="", n=int(a.context)))
    if not diff:
        print("\n(target đã khớp nội dung proposal — có thể discard)")
        return 0
    print()
    print("\n".join(diff))
    return 0


def cmd_apply(a: argparse.Namespace) -> int:
    p = _resolve(a.name)
    if p is None:
        return 1
    meta, content = parse(p)
    if a.target:
        meta = dict(meta, target=a.target)
    dest = target_path(meta, p.name)
    if dest is None:
        print("[ERROR] không xác định được target từ metadata của proposal "
              "(file cũ trước khi có metadata).")
        guess = guess_target(p.name)
        if not guess.startswith("?"):
            print(f"  Page khớp duy nhất trên đĩa: {guess}")
        print("  Xác nhận tường minh: llm-wiki proposals apply "
              f"{p.name} --target wiki/<domain>/<kind>/<slug>.md")
        return 1
    existed = dest.exists()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    p.unlink()
    rel = dest.relative_to(wiki_root()).as_posix()
    # Contract cho CLI (2 dòng máy đọc được): legacy `APPLIED\t<rel>` + JSON
    # `RESULT {...}`. Giữ cả hai — base cũ chỉ có dòng đầu, CLI mới đọc JSON trước.
    print(f"APPLIED\t{rel}")
    print(f'RESULT {{"status": "applied", "target": "{rel}"}}')
    print(f"✓ applied → {rel} ({'sửa' if existed else 'tạo mới'}), đã xoá proposal")

    _log_entry(rel, p.name)
    _reindex(rel, dest)
    print()
    print(f"Duyệt nội dung (chữ ký của bạn, AI không tự set được):")
    print(f"  llm-wiki verify {rel} --by <human-id>")
    return 0


def cmd_discard(a: argparse.Namespace) -> int:
    p = _resolve(a.name)
    if p is None:
        return 1
    if not a.force:
        meta, _ = parse(p)
        print(f"Sẽ XOÁ proposal {p.name} (target: {meta.get('target') or '?'}). "
              f"Chạy lại với --force để xác nhận.")
        return 1
    p.unlink()
    print(f"✓ discarded {p.name}")
    return 0


def cmd_new(a: argparse.Namespace) -> int:
    """Tạo proposal mới từ 1 file nội dung (hoặc stdin)."""
    content = sys.stdin.read() if a.file == "-" else Path(a.file).resolve().read_text(
        encoding="utf-8")
    prop = stage(wiki_root(), a.target, content, by=a.by, note=a.note)
    print(f"✓ proposal: {prop.name}  target={a.target}")
    print(f"  xem: llm-wiki proposals show {prop.name}")
    return 0


# ───────────────────────────────────────────────────────────── helpers

def _resolve(name: str) -> Path | None:
    d = proposals_dir()
    cand = (d / name)
    if cand.is_file():
        return cand
    matches = [p for p in (d.glob(f"*{name}*") if d.is_dir() else []) if p.is_file()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        print(f"[ERROR] không tìm thấy proposal '{name}'. Chạy `llm-wiki proposals list`.")
    else:
        print(f"[ERROR] '{name}' khớp {len(matches)} proposal — cần tên đầy đủ:")
        for m in matches:
            print(f"  {m.name}")
    return None


def _log_entry(rel: str, prop_name: str) -> None:
    """Append entry vào `wiki/log.md` theo thứ tự reverse-chronological (mới trên)."""
    log = wiki_root() / "wiki" / "log.md"
    now = datetime.datetime.now()
    line = (f"## [{now.strftime('%Y-%m-%d %H:%M:%S')}] proposals-apply | {rel}"
            f" — từ {prop_name}")
    if not log.exists():
        log.write_text(f"{line}\n", encoding="utf-8")
        return
    lines = log.read_text(encoding="utf-8").splitlines()
    at = next((i for i, l in enumerate(lines) if l.startswith("## [")), len(lines))
    lines.insert(at, line)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _reindex(rel: str, dest: Path) -> None:
    """Index lại page vừa apply — gọi hàm trực tiếp, không spawn subprocess con."""
    try:
        import search
        conn = db.get_conn()
        db.init_db(conn)
        search.index_file_at(conn, str(dest))
        print(f"✓ indexed {rel}")
    except Exception as e:                     # noqa: BLE001 — index fail không mất nội dung
        print(f"[warn] chưa index được {rel}: {e}")
        print("  Chạy: llm-wiki reindex")


def main() -> int:
    ap = argparse.ArgumentParser(description="Quản lý wiki/.proposals/ (staging edits)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Liệt kê proposal + diff size so với target")

    s = sub.add_parser("show", help="Metadata + unified diff của proposal")
    s.add_argument("name")
    s.add_argument("--context", "-C", default=3, help="Số dòng ngữ cảnh quanh diff")

    a = sub.add_parser("apply", help="Ghi proposal vào target, xoá proposal, reindex")
    a.add_argument("name")
    a.add_argument("--target", help="Ép target path (cho proposal cũ không có metadata)")

    d = sub.add_parser("discard", help="Xoá proposal, không ghi gì")
    d.add_argument("name")
    d.add_argument("--force", "-f", action="store_true")

    n = sub.add_parser("new", help="Tạo proposal có metadata (dùng bởi MCP tool)")
    n.add_argument("--target", required=True, help="Path tương đối trong wiki")
    n.add_argument("--file", required=True, help="File chứa nội dung, hoặc '-' cho stdin")
    n.add_argument("--by", default="", help="AI tool/client đề xuất")
    n.add_argument("--note", default="")

    args = ap.parse_args()
    handlers = {"list": cmd_list, "show": cmd_show, "apply": cmd_apply,
                "discard": cmd_discard, "new": cmd_new}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
