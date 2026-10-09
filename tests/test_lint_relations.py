"""Task 5: lint rules cho typed relations + claims (spec §8 severity table).

Pattern: tmp wiki root + in-memory DB (cùng tests/test_reserved_index.py).
Mỗi test viết page file + upsert row (lint chỉ iterate pages có trong DB),
rồi chạy lint.lint(conn, wiki_root=...) và assert trên result["findings"].
"""
import os
import sys


def _load_lint(tmp_path, monkeypatch, toml=None):
    """WIKI_ROOT → tmp; purge module cache; trả (db, lint, conn in-memory)."""
    monkeypatch.setenv("WIKI_ROOT", str(tmp_path))
    base_tools = os.path.join("src", "llm_wiki_base", "base_tools")
    monkeypatch.syspath_prepend(os.path.abspath(base_tools))
    for mod in [m for m in list(sys.modules) if m in (
            "db", "search", "chunking", "config_file", "embed", "paths",
            "llm_wiki_base.paths", "llm_wiki_base.config_file",
            "graph", "lint")]:
        del sys.modules[mod]
    if toml is not None:
        (tmp_path / ".llm-wiki-base.toml").write_text(toml, encoding="utf-8")
    import db
    import lint
    conn = db.get_conn(":memory:")
    db.init_db(conn)
    return db, lint, conn


def _page(db, conn, tmp_path, rel, txt, title="p", domain="tech", kind="concept"):
    """Viết file + upsert row pages (lint không thấy file chưa có row)."""
    fp = tmp_path / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(txt, encoding="utf-8")
    db.upsert_page(conn, rel, title, domain, kind, txt, 0.0)
    return rel


def _target(tmp_path, rel):
    """File target tồn tại trên disk (không cần row — chỉ check existence)."""
    fp = tmp_path / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("# target\n", encoding="utf-8")


def _msgs(result, path=None):
    if path is not None:
        return result["findings"].get(path, [])
    return [m for msgs in result["findings"].values() for m in msgs]


_JP_TOML = '[langpack]\nenabled = true\npack = "japanese"\n'


def test_broken_relation_target(tmp_path, monkeypatch):
    """Frontmatter relation trỏ file không tồn tại → broken-relation-target (CRITICAL)."""
    db, lint, conn = _load_lint(tmp_path, monkeypatch)
    path = _page(db, conn, tmp_path, "wiki/languages/grammar-point/ba.md",
        "---\n"
        "title: ba\n"
        "domain: languages\n"
        "kind: grammar-point\n"
        "relations:\n"
        "  - rel: contrast-with\n"
        "    target: wiki/languages/grammar-point/missing.md\n"
        '    note: "điều kiện 〜たら"\n'
        "---\n\n"
        "# ba\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    msgs = _msgs(result, path)
    assert any("broken-relation-target" in m for m in msgs)
    assert any("(CRITICAL)" in m for m in msgs if "broken-relation-target" in m)
    assert result["critical_count"] >= 1


def test_plain_wikilink_no_broken_relation_target(tmp_path, monkeypatch):
    """Plain [[missing]] là edge `related` — đã có broken-wikilink WARNING.

    KHÔNG được nổ thêm broken-relation-target (CRITICAL) trên cùng edge:
    wiki không pack phải giữ nguyên exit behavior (zero behavior change).
    """
    db, lint, conn = _load_lint(tmp_path, monkeypatch)
    path = _page(db, conn, tmp_path, "wiki/tech/concept/a.md",
        "---\ntitle: a\ndomain: tech\nkind: concept\n---\n\n# a\n\n"
        "[[wiki/tech/concept/gone.md]]\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    msgs = _msgs(result, path)
    assert any("broken-wikilink" in m for m in msgs)  # rule cũ giữ nguyên
    assert not any("broken-relation-target" in m for m in msgs)
    assert result["critical_count"] == 0  # không có critical mới → exit 0


def test_unknown_rel_type(tmp_path, monkeypatch):
    """Rel lạ khi japanese pack bật → unknown-rel-type (CRITICAL), prefix đầu message."""
    db, lint, conn = _load_lint(tmp_path, monkeypatch, toml=_JP_TOML)
    _target(tmp_path, "wiki/tech/concept/x.md")
    path = _page(db, conn, tmp_path, "wiki/tech/concept/a.md",
        "---\ntitle: a\ndomain: tech\nkind: concept\n---\n\n# a\n\n"
        "[[wiki/tech/concept/x.md|rel:vague-rel]]\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    msgs = _msgs(result, path)
    assert any(m.startswith("unknown-rel-type") for m in msgs)
    assert result["critical_count"] == 1  # đúng 1 critical (target tồn tại)


def test_relation_target_kind_distinct_prefix(tmp_path, monkeypatch):
    """covered-in (targets=[source]) trỏ concept/ → token riêng relation-target-kind,
    KHÔNG gộp vào unknown-rel-type (controller ruling từ Task 4)."""
    db, lint, conn = _load_lint(tmp_path, monkeypatch, toml=_JP_TOML)
    _target(tmp_path, "wiki/tech/concept/x.md")
    path = _page(db, conn, tmp_path, "wiki/tech/concept/a.md",
        "---\ntitle: a\ndomain: tech\nkind: concept\nrelations:\n"
        "  - rel: covered-in\n"
        "    target: wiki/tech/concept/x.md\n"
        "---\n\n# a\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    msgs = _msgs(result, path)
    assert any(m.startswith("relation-target-kind") for m in msgs)
    assert not any(m.startswith("unknown-rel-type") for m in msgs)
    assert result["critical_count"] == 1


def test_claim_without_footnote(tmp_path, monkeypatch):
    """Bullet trong ## Claims thiếu [^id] → claim-without-footnote (CRITICAL).

    Bullet cùng tên ngoài section Claims KHÔNG bị flag.
    """
    db, lint, conn = _load_lint(tmp_path, monkeypatch)
    path = _page(db, conn, tmp_path, "wiki/tech/concept/c.md",
        "---\ntitle: c\ndomain: tech\nkind: concept\n---\n\n# c\n\n"
        "## Claims\n\n"
        "- Claim không footnote.\n\n"
        "## Other\n\n"
        "- Bullet ngoài Claims không cần footnote.\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    msgs = _msgs(result, path)
    claim_msgs = [m for m in msgs if "claim-without-footnote" in m]
    assert len(claim_msgs) == 1  # chỉ bullet trong ## Claims
    assert result["critical_count"] == 1


def test_relation_without_note_contrast(tmp_path, monkeypatch):
    """contrast-with không note → relation-without-note, đánh dấu (advisory)."""
    db, lint, conn = _load_lint(tmp_path, monkeypatch)
    _target(tmp_path, "wiki/tech/concept/x.md")
    path = _page(db, conn, tmp_path, "wiki/tech/concept/a.md",
        "---\ntitle: a\ndomain: tech\nkind: concept\n---\n\n# a\n\n"
        "[[wiki/tech/concept/x.md|rel:contrast-with]]\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    msgs = _msgs(result, path)
    note_msgs = [m for m in msgs if "relation-without-note" in m]
    assert len(note_msgs) == 1
    assert "(advisory)" in note_msgs[0]
    assert result["critical_count"] == 0  # advisory không tính vào critical


def test_inline_rel_vs_alias(tmp_path, monkeypatch):
    """Cùng dst: inline `rel:contrast-with` + alias [[dst|contrast-with]] —
    alias note TRÙNG tên typed rel (nhìn như rel, spec §11) → conflict set có
    typed edge + rel-shaped alias → inline-rel-vs-alias (advisory).

    Mention trần/alias thường KHÔNG đếm → xem
    test_canonical_frontmatter_prose_no_finding.
    """
    db, lint, conn = _load_lint(tmp_path, monkeypatch)
    _target(tmp_path, "wiki/tech/concept/x.md")
    path = _page(db, conn, tmp_path, "wiki/tech/concept/a.md",
        "---\ntitle: a\ndomain: tech\nkind: concept\n---\n\n# a\n\n"
        "[[wiki/tech/concept/x.md|rel:contrast-with]]\n"
        "[[wiki/tech/concept/x.md|contrast-with]]\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    msgs = _msgs(result, path)
    alias_msgs = [m for m in msgs if "inline-rel-vs-alias" in m]
    assert len(alias_msgs) == 1
    assert "(advisory)" in alias_msgs[0]
    assert result["critical_count"] == 0


def test_canonical_frontmatter_prose_no_finding(tmp_path, monkeypatch):
    """Shape chuẩn spec §7 (ingest synthesis sẽ viết): fm covered-in → source
    page + mention trần trong prose → default edge 'related' KHÔNG tham gia
    conflict set → không inline-rel-vs-alias. Alias thường (không phải tên
    rel) cũng không đếm. Zero change: critical_count == 0 (exit 0)."""
    db, lint, conn = _load_lint(tmp_path, monkeypatch)
    _target(tmp_path, "wiki/languages/source/shinkanzen3.md")
    _target(tmp_path, "wiki/languages/source/minna1.md")
    _page(db, conn, tmp_path, "wiki/languages/concept/ba.md",
        "---\ntitle: ba\ndomain: languages\nkind: concept\nrelations:\n"
        "  - rel: covered-in\n"
        "    target: wiki/languages/source/shinkanzen3.md\n"
        "  - rel: example-of\n"
        "    target: wiki/languages/source/minna1.md\n"
        "---\n\n# ba\n\n"
        "Nguồn: [[wiki/languages/source/shinkanzen3.md]] (bài 6).\n"
        "Xem thêm [[wiki/languages/source/minna1.md|Minna]] (alias thường).\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    assert not any("inline-rel-vs-alias" in m for m in _msgs(result))
    assert result["critical_count"] == 0


def test_no_pack_no_unknown_rel(tmp_path, monkeypatch):
    """Không có [langpack] → không validate gì cả (regression: wiki không pack
    giữ nguyên hành vi — kể cả targets constraint)."""
    db, lint, conn = _load_lint(tmp_path, monkeypatch)  # không có toml
    _target(tmp_path, "wiki/tech/concept/x.md")
    _page(db, conn, tmp_path, "wiki/tech/concept/a.md",
        "---\ntitle: a\ndomain: tech\nkind: concept\nrelations:\n"
        "  - rel: vague-rel\n"
        "    target: wiki/tech/concept/x.md\n"
        "  - rel: covered-in\n"
        "    target: wiki/tech/concept/x.md\n"
        "---\n\n# a\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    all_msgs = _msgs(result)
    assert not any("unknown-rel-type" in m for m in all_msgs)
    assert not any("relation-target-kind" in m for m in all_msgs)
    assert not any("langpack-field-missing" in m for m in all_msgs)
    assert result["critical_count"] == 0


def test_langpack_field_missing(tmp_path, monkeypatch):
    """Pack on: page grammar-point thiếu required field → langpack-field-missing
    (CRITICAL); page đủ fields → không finding."""
    db, lint, conn = _load_lint(tmp_path, monkeypatch, toml=_JP_TOML)
    missing = _page(db, conn, tmp_path, "wiki/languages/grammar-point/ba.md",
        "---\ntitle: ba\ndomain: languages\nkind: grammar-point\n---\n\n# ba\n")
    ok = _page(db, conn, tmp_path, "wiki/languages/grammar-point/te.md",
        "---\ntitle: te\ndomain: languages\nkind: grammar-point\n"
        "pattern: 〜てから\nmeaning: sau khi X xảy thì Y\n---\n\n# te\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))
    miss_msgs = [m for m in _msgs(result, missing)
                 if "langpack-field-missing" in m]
    assert len(miss_msgs) == 2  # pattern + meaning đều required
    assert all("(CRITICAL)" in m for m in miss_msgs)
    assert not any("langpack-field-missing" in m for m in _msgs(result, ok))
    assert result["critical_count"] == 2


def test_langpack_config_error_no_crash(tmp_path, monkeypatch):
    """Pack không tồn tại → load_langpack raise, nhưng lint PHẢI trả kết quả:
    1 finding CRITICAL langpack-config-error, không exception, các rule khác chạy."""
    db, lint, conn = _load_lint(
        tmp_path, monkeypatch,
        toml='[langpack]\nenabled = true\npack = "nonexistent"\n')
    _target(tmp_path, "wiki/tech/concept/x.md")  # target tồn tại → chỉ 1 critical
    _page(db, conn, tmp_path, "wiki/tech/concept/a.md",
        "---\ntitle: a\ndomain: tech\nkind: concept\n---\n\n# a\n\n"
        "[[wiki/tech/concept/x.md|rel:vague-rel]]\n")
    result = lint.lint(conn, wiki_root=str(tmp_path))  # không được raise
    err = [m for m in _msgs(result) if "langpack-config-error" in m]
    assert len(err) == 1
    assert err[0].startswith("langpack-config-error:")
    assert "(CRITICAL)" in err[0]
    assert "nonexistent" in err[0]  # message gốc được giữ lại
    # Pack không load được → validate/fields skip (fail-visible, không fail-open
    # âm thầm): không có unknown-rel-type dù rel lạ.
    assert not any("unknown-rel-type" in m for m in _msgs(result))
    assert result["critical_count"] == 1
