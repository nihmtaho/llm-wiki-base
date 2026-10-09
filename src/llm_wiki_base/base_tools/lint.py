import os
import re
import sys
from datetime import datetime

import db
import graph
from config_file import get_config

_URL_RE = re.compile(r"^https?://")
# Chỉ flag local path cho raw/inbox/ (staging, không stable để cite).
# raw/ (ngoài inbox) là local cache do user quản lý, có thể commit + cite.
_LOCAL_RE = re.compile(r"^raw/inbox/.+\.md$", re.IGNORECASE)

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_FOOTNOTE_REF_RE = re.compile(r"\[\^([A-Za-z0-9_-]+)\]")
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([A-Za-z0-9_-]+)\]:", re.MULTILINE)
_DENSE_BULLET_RE = re.compile(r"(?:^|\s)-\s")

STATUS_VOCAB = {"draft", "active", "done", "stale", "planned", "deprecated", "superseded"}
CONFIDENCE_VOCAB = {"unverified", "human-verified", "machine-confirmed", "superseded"}


def _parse_iso(s: str):
    """Parse ISO-8601 datetime ('Z' → +00:00). Trả datetime hoặc None."""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _split_frontmatter(txt: str) -> tuple[str, str]:
    """Trả (fm_raw, body). fm_raw rỗng nếu không có frontmatter."""
    m = _FM_RE.match(txt)
    if not m:
        return "", txt
    return m.group(1), txt[m.end():]


def _code_skip_ranges(txt: str) -> list[tuple[int, int]]:
    """Range các code block ``` và code span ` — check bỏ qua match trong này."""
    skip: list[tuple[int, int]] = []
    for m in re.finditer(r"```[^\n]*\n.*?```", txt, re.DOTALL):
        skip.append((m.start(), m.end()))
    for m in re.finditer(r"`[^`\n]+`", txt):
        if not any(s <= m.start() < e for s, e in skip):
            skip.append((m.start(), m.end()))
    return skip


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
    """
    skip_ranges = _code_skip_ranges(txt)

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


def _check_layout(path: str, body: str, lcfg: dict, add) -> None:
    """Layout checks từ [lint] config: banned-terms, dense-bullet, indent-depth (advisory)."""
    skip_ranges = _code_skip_ranges(body)
    lines = body.split("\n")
    max_bullets = int(lcfg.get("max_bullet_items", 3) or 3)
    max_depth = int(lcfg.get("max_indent_depth", 3) or 3)
    for i, line in enumerate(lines):
        pos = sum(len(ln) + 1 for ln in lines[:i])
        if any(s <= pos < e for s, e in skip_ranges) or not line.strip():
            continue
        n_bullets = len(_DENSE_BULLET_RE.findall(line))
        if n_bullets > max_bullets:
            add(path, f"dense-bullet (line {i + 1}): {n_bullets} mục dồn một dòng (> {max_bullets}) — tách dòng")
            continue
        spaces = len(line) - len(line.lstrip(" "))
        tabs = len(line) - len(line.lstrip("\t"))
        depth = spaces // 2 + tabs
        if depth > max_depth:
            add(path, f"indent-depth (line {i + 1}): thụt lề {depth} cấp (> {max_depth})")
    for term in lcfg.get("banned_terms", []) or []:
        if term and term.lower() in body.lower():
            add(path, f"banned-terms: '{term}' xuất hiện trong page (advisory)")


def _check_frontmatter(path: str, fm: dict, body: str, add, today) -> None:
    """Conformance frontmatter: field bắt buộc, vocab status/confidence, timestamp, footnote↔sources."""
    if not fm:
        add(path, "missing-frontmatter: page trong wiki/ phải có frontmatter YAML hợp lệ")
        return
    for key in ("title", "domain", "kind"):
        if not str(fm.get(key) or "").strip():
            add(path, f"missing-frontmatter: thiếu `{key}`")
    st = str(fm.get("status") or "").strip()
    if st and st not in STATUS_VOCAB:
        add(path, f"status-vocab: status '{st}' ∉ {sorted(STATUS_VOCAB)}")
    cf = str(fm.get("confidence") or "").strip()
    if cf and cf not in CONFIDENCE_VOCAB:
        add(path, f"status-vocab: confidence '{cf}' ∉ {sorted(CONFIDENCE_VOCAB)}")
    upd = str(fm.get("updated") or "").strip()
    if upd and not _DATE_RE.match(upd):
        add(path, f"timestamp-format: updated '{upd}' không khớp YYYY-MM-DD")
    stale_after = str(fm.get("stale_after") or "").strip()
    if stale_after:
        dt = _parse_iso(stale_after)
        if dt is None:
            add(path, f"timestamp-format: stale_after '{stale_after}' không phải ISO-8601")
        elif dt.date() < today:
            add(path, f"stale-after-passed: stale_after={stale_after} đã quá hạn — review/renew (không tự đổi)")
    for k in ("verified", "generated"):
        v = fm.get(k)
        if isinstance(v, dict):
            at = str(v.get("at") or "").strip()
            if at and _parse_iso(at) is None:
                add(path, f"timestamp-format: {k}.at '{at}' không phải ISO-8601")
    # footnote ↔ sources (chỉ khi sources là list-of-dicts có id — dual-format)
    srcs = fm.get("sources")
    if isinstance(srcs, list) and srcs and all(isinstance(s, dict) for s in srcs):
        ids = {str(s.get("id") or "").strip() for s in srcs} - {""}
        refs = set(_FOOTNOTE_REF_RE.findall(body))
        defs = set(_FOOTNOTE_DEF_RE.findall(body))
        dangling = (refs - defs) - ids
        for x in sorted(dangling):
            add(path, f"footnote-sources-match: [^{x}] được cite nhưng không có trong sources[].id")
        unused = ids - refs
        for x in sorted(unused):
            add(path, f"footnote-sources-match: sources[].id '{x}' chưa được cite ([^{x}])")


def _check_wikilinks(path: str, txt: str, WIKI_ROOT: str, add, linked: set) -> None:
    """Wikilink target phải tồn tại trên disk (gap cũ: lint chỉ dùng link để tính orphan)."""
    skip_ranges = _code_skip_ranges(txt)
    for m in _WIKILINK_RE.finditer(txt):
        if any(s <= m.start() < e for s, e in skip_ranges):
            continue
        target = m.group(1).split("|")[0].strip().split("#")[0].strip()
        if not target or _URL_RE.match(target):
            continue
        norm = target if target.endswith(".md") else target + ".md"
        linked.add(os.path.normpath(norm))
        if not os.path.exists(os.path.join(WIKI_ROOT, norm)):
            line_no = txt[: m.start()].count("\n") + 1
            add(path, f"broken-wikilink (line {line_no}): [[{target}]] trỏ tới file không tồn tại")


def _check_relations(path: str, txt: str, WIKI_ROOT: str, add, pack) -> list[str]:
    """Typed-relation + claims rules (spec §8). Trả list message CRITICAL (đã add).

    - `broken-relation-target` (CRITICAL): dst của link (typed lẫn default edge
      `related`) trỏ file không tồn tại — links table có edge gãy (spec §4.2).
      Strip `#anchor` trước khi check (anchor là section-level, §5.3).
    - `unknown-rel-type` / `relation-target-kind` (CRITICAL): validate_links
      theo langpack — string pass-through (validate_links đã gắn đúng token;
      ruling Task 4: 2 token RIÊNG, không gộp).
    - `langpack-field-missing` (CRITICAL): page khớp kind `path` của pack thiếu
      required field trong frontmatter (chỉ khi pack on).
    - `claim-without-footnote` (CRITICAL): bullet trong `## Claims` không cite
      `[^id]` (§5.3 — mỗi bullet = 1 claim atom kèm provenance).
    - `relation-without-note` (advisory): contrast-with/contradicts không note.
    - `inline-rel-vs-alias` (advisory): cùng dst nhưng nhiều định nghĩa rel khác
      nhau — typed vs plain-alias, hoặc 2 typed khác rel (§5.2).

    Tất cả qua `add` (channel findings chung): advisory gắn hậu tố "(advisory)"
    (cùng mẫu banned-terms), CRITICAL gắn "(CRITICAL)" + được trả về để lint()
    cộng vào `critical_count`. Không rule nào auto-fix (spec §8: chỉ content
    re-derivable mới được --fix).
    """
    critical: list[str] = []

    def _add_critical(msg: str) -> None:
        full = f"{msg} (CRITICAL)"
        add(path, full)
        critical.append(full)

    links = graph.extract_links(txt)

    # broken-relation-target — check existence như _check_wikilinks, có thêm
    # typed edges (graph.extract_links không cho vị trí → không có line number).
    for link in links:
        dst = link.dst.split("#", 1)[0].strip()
        if not dst or _URL_RE.match(dst):
            continue
        norm = dst if dst.endswith(".md") else dst + ".md"
        if not os.path.exists(os.path.join(WIKI_ROOT, norm)):
            _add_critical(
                f"broken-relation-target: rel {link.rel!r} → {link.dst!r} "
                f"trỏ tới file không tồn tại"
            )

    if pack is not None:
        # unknown-rel-type / relation-target-kind — pass-through string có sẵn
        # token; severity gắn thêm, không sửa nội dung error.
        for err in graph.validate_links(links, pack):
            _add_critical(err)

        # langpack-field-missing — page dưới kind path của pack thiếu required
        # field (db.parse_frontmatter — cùng parser frontmatter với lint).
        fm = db.parse_frontmatter(txt)
        for kind_name, kspec in (pack.get("kinds") or {}).items():
            if not isinstance(kspec, dict):
                continue
            kpath = str(kspec.get("path") or "").strip("/")
            if not kpath or f"/{kpath}/" not in f"/{path}":
                continue
            for fname, fspec in (kspec.get("fields") or {}).items():
                if not (isinstance(fspec, dict) and fspec.get("required")):
                    continue
                val = fm.get(fname)
                if (val is None
                        or (isinstance(val, str) and not val.strip())
                        or (isinstance(val, (list, dict)) and not val)):
                    _add_critical(
                        f"langpack-field-missing: page thuộc kind {kind_name!r} "
                        f"thiếu required field {fname!r}"
                    )

    # claim-without-footnote — quét section ## Claims (cùng ngữ nghĩa section
    # với graph.extract_links: H2 Claims bật, H2 khác tắt; code fence bỏ qua).
    skip = _code_skip_ranges(txt)
    lines = txt.split("\n")
    in_claims = False
    for i, line in enumerate(lines):
        pos = sum(len(ln) + 1 for ln in lines[:i])
        if any(s <= pos < e for s, e in skip):
            continue
        if re.match(r"^## Claims(?:\s|$)", line):
            in_claims = True
            continue
        if in_claims and re.match(r"^##\s", line):
            in_claims = False
            continue
        if in_claims and line.strip().startswith("- ") and "[^" not in line:
            _add_critical(
                f"claim-without-footnote (line {i + 1}): bullet trong ## Claims "
                f"thiếu footnote [^id]"
            )

    # relation-without-note (advisory) — contrast/contradicts cần context (§8).
    # Link trong ## Claims đã được graph lấy note từ bullet sở hữu → không flag.
    for link in links:
        if link.rel in ("contrast-with", "contradicts") \
                and not (link.note or "").strip():
            add(path, f"relation-without-note: rel {link.rel!r} → {link.dst!r} "
                      f"không có note (advisory)")

    # inline-rel-vs-alias (advisory) — cùng dst, nhiều định nghĩa rel (§5.2):
    # plain [[dst]] → rel 'related' + typed [[dst|rel:X]] → 2 rel khác nhau.
    rels_by_dst: dict[str, set[str]] = {}
    for link in links:
        rels_by_dst.setdefault(link.dst, set()).add(link.rel)
    for dst in sorted(rels_by_dst):
        rels = rels_by_dst[dst]
        if len(rels) > 1:
            add(path, f"inline-rel-vs-alias: {dst!r} có nhiều định nghĩa rel "
                      f"khác nhau: {', '.join(sorted(rels))} (advisory)")

    return critical


def _check_pins(WIKI_ROOT: str, add) -> None:
    """Pin `active` trong wiki/pins.yml: concept tồn tại + anchor heading còn đó (orphan → human xử lý)."""
    pins_fp = os.path.join(WIKI_ROOT, "wiki", "pins.yml")
    if not os.path.exists(pins_fp):
        return
    with open(pins_fp, encoding="utf-8") as f:
        txt = f.read()
    for block in re.split(r"\n(?=\s*-\s+concept:)", txt):
        m_c = re.search(r"^-\s*concept:\s*(.+)$", block, re.MULTILINE)
        if not m_c:
            continue
        concept = m_c.group(1).strip().strip("\"'")
        m_s = re.search(r"^\s*status:\s*(.+)$", block, re.MULTILINE)
        status = (m_s.group(1).strip().strip("\"'") if m_s else "active")
        if status != "active":
            continue
        page_fp = os.path.join(WIKI_ROOT, concept if concept.endswith(".md") else concept + ".md")
        if not os.path.exists(page_fp):
            add("wiki/pins.yml", f"pin-orphan: concept '{concept}' không tồn tại — cần human xử lý (không tự xoá pin)")
            continue
        m_a = re.search(r"^\s*anchor:\s*(.+)$", block, re.MULTILINE)
        if not m_a:
            continue
        anchor = m_a.group(1).strip().strip("\"'")
        with open(page_fp, encoding="utf-8") as f:
            page_txt = f.read()
        if anchor not in {ln.strip() for ln in page_txt.split("\n")}:
            add("wiki/pins.yml", f"pin-orphan: anchor '{anchor}' không còn trong '{concept}' — pin cần human xử lý")


def lint(conn, wiki_root=None) -> dict:
    """Health-check deterministic: orphan, broken link, missing file, frontmatter
    conformance, timestamp, footnote↔sources, index sync, pins, layout,
    typed-relation + claims rules (broken target, unknown rel, pack fields,
    claim provenance — spec §8).

    Critical issues (missing_file) indicate DB rows trỏ file không tồn tại —
    search trả row này nhưng file gone → broken result cho user. Relation/claim
    criticals (spec §8) cũng tính vào critical_count — không auto-fix.

    `wiki_root` override cho centralized MCP server (multi-wiki). Nếu None,
    dùng db.WIKI_ROOT module default.
    """
    WIKI_ROOT = wiki_root or db.WIKI_ROOT
    lcfg = get_config(WIKI_ROOT).get("lint", {})
    # Langpack một lần per run: None khi wiki không bật [langpack] →
    # _check_relations bỏ qua validate/fields (zero change cho wiki không pack).
    # Bật mà pack hỏng → load_langpack fail loud (FileNotFoundError/ValueError)
    # đúng contract của graph — lint không fail-open thầm lặng.
    pack = graph.load_langpack(WIKI_ROOT)
    today = datetime.now().date()
    pages = db.list_pages(conn)
    linked = set()
    orphan = []
    missing_file = []
    rel_critical: list[str] = []  # message CRITICAL từ _check_relations
    findings: dict[str, list[str]] = {}  # path → [msgs]

    def add(path: str, msg: str) -> None:
        findings.setdefault(path, []).append(msg)

    wiki_pages = [p for p in pages if p["path"].startswith("wiki/")]

    for p in wiki_pages:
        # Chỉ lint file trong wiki/. raw/ là intermediate, không tuân theo wiki schema.
        full = os.path.join(WIKI_ROOT, p["path"])
        if not os.path.exists(full):
            missing_file.append(p["path"])
            continue
        with open(full, encoding="utf-8") as f:
            txt = f.read()
        for m in _check_sources_local_path(p["path"], txt):
            add(p["path"], m)
        for m in _check_body_inline_local_refs(p["path"], txt):
            add(p["path"], m)
        _check_wikilinks(p["path"], txt, str(WIKI_ROOT), add, linked)
        rel_critical.extend(
            _check_relations(p["path"], txt, str(WIKI_ROOT), add, pack))
        if p["path"] not in ("wiki/index.md", "wiki/log.md"):
            fm_raw, body = _split_frontmatter(txt)
            _check_frontmatter(p["path"], db.parse_frontmatter(txt), body, add, today)
            _check_layout(p["path"], body, lcfg, add)

    for p in wiki_pages:
        if p["path"] == "wiki/index.md":
            continue
        if os.path.normpath(p["path"]) not in linked:
            orphan.append(p["path"])

    # index-entry + domain index existence
    wiki_dir = os.path.join(WIKI_ROOT, "wiki")
    domain_index_cache: dict[str, str] = {}
    missing_index_domains: set[str] = set()
    if os.path.isdir(wiki_dir):
        for p in wiki_pages:
            if p["path"] in ("wiki/index.md", "wiki/log.md"):
                continue
            parts = p["path"].split("/")
            if len(parts) < 3:
                continue
            domain = parts[1]
            idx_fp = os.path.join(wiki_dir, domain, "index.md")
            if not os.path.exists(idx_fp):
                if domain not in missing_index_domains:
                    missing_index_domains.add(domain)
                    add(f"wiki/{domain}", f"domain-missing-index: domain '{domain}' chưa có index.md")
                continue
            if domain not in domain_index_cache:
                with open(idx_fp, encoding="utf-8") as f:
                    domain_index_cache[domain] = f.read()
            slug = os.path.splitext(os.path.basename(p["path"]))[0]
            if slug not in domain_index_cache[domain]:
                add(p["path"], f"missing-index-entry: chưa được liệt kê trong wiki/{domain}/index.md")

    _check_pins(str(WIKI_ROOT), add)

    return {
        "page_count": len(pages),
        "orphans": orphan,
        "missing_file": missing_file,
        "findings": findings,
        # CRITICAL = dangling rows (fix-able) + relation/claim criticals theo
        # spec §8 (không auto-fix). Advisory chỉ nằm trong findings.
        "critical_count": len(missing_file) + len(rel_critical),
        "note": "Contradiction là report cho human, không materialize thành edge. Semantic checks (mâu thuẫn, stale claim) là việc của review skill.",
    }


def fix_missing_files(conn, wiki_root=None) -> list[str]:
    """Xóa rows trong `pages` có path không tồn tại trên disk. Trả list path đã xóa.

    `wiki_root` override cho centralized MCP server (multi-wiki).
    """
    WIKI_ROOT = wiki_root or db.WIKI_ROOT
    pages = db.list_pages(conn)
    deleted = []
    for p in pages:
        full = os.path.join(WIKI_ROOT, p["path"])
        if not os.path.exists(full):
            conn.execute("DELETE FROM pages WHERE path = ?", (p["path"],))
            deleted.append(p["path"])
    conn.commit()
    conn.execute("DELETE FROM pages_fts WHERE rowid NOT IN (SELECT id FROM pages)")
    conn.execute("DELETE FROM chunks_fts WHERE page_id NOT IN (SELECT id FROM pages)")
    conn.commit()
    return deleted


def fix_index_entries(wiki_root=None) -> list[str]:
    """Auto-fix an toàn: thêm entry còn thiếu vào `wiki/<domain>/index.md`
    (additive — không xoá/sửa nội dung có sẵn), tạo index.md cho domain thiếu.
    Trả list rel-path page đã được thêm entry.
    """
    import glob as _glob

    WIKI_ROOT = wiki_root or db.WIKI_ROOT
    wiki_dir = os.path.join(WIKI_ROOT, "wiki")
    fixed: list[str] = []
    if not os.path.isdir(wiki_dir):
        return fixed
    domains = sorted(
        d for d in os.listdir(wiki_dir)
        if os.path.isdir(os.path.join(wiki_dir, d)) and not d.startswith(".")
    )
    for domain in domains:
        domain_dir = os.path.join(wiki_dir, domain)
        idx_fp = os.path.join(domain_dir, "index.md")
        if not os.path.exists(idx_fp):
            with open(idx_fp, "w", encoding="utf-8") as f:
                f.write(f"# {domain}\n\n")
            print(f"  created wiki/{domain}/index.md")
        with open(idx_fp, encoding="utf-8") as f:
            idx_text = f.read()
        pages = sorted(
            fp for fp in _glob.glob(os.path.join(domain_dir, "**", "*.md"), recursive=True)
            if os.path.basename(fp) != "index.md"
        )
        missing = []
        for fp in pages:
            slug = os.path.splitext(os.path.basename(fp))[0]
            if slug in idx_text:
                continue
            with open(fp, encoding="utf-8") as f:
                page_txt = f.read()
            title = None
            for ln in page_txt.split("\n"):
                if ln.startswith("# "):
                    title = ln[2:].strip()
                    break
            title = title or slug
            rel = os.path.relpath(fp, WIKI_ROOT).replace(os.sep, "/")
            missing.append(f"- [[{rel[:-len('.md')]}|{title}]]")
            fixed.append(rel)
        if missing:
            with open(idx_fp, "a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(missing) + "\n")
            print(f"  + {len(missing)} entry vào wiki/{domain}/index.md")
    return fixed


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
        fixed = fix_index_entries()
        if not fixed:
            print("index entries up-to-date")
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
        n_missing = len(result["missing_file"])
        n_rel = result["critical_count"] - n_missing
        if n_missing:
            print(
                f"\n{n_missing} critical issue(s) — run `python tools/lint.py --fix` to delete dangling rows"
            )
        if n_rel:
            print(
                f"\n{n_rel} critical relation/claim finding(s) — fix by hand ở findings phía trên (không có auto-fix, spec §8)"
            )
        sys.exit(1)
