"""Task 1: graph.py — pure, deterministic typed-relation link extraction."""
import os
import sys


def _load_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_path))
    base_tools = os.path.join("src", "llm_wiki_base", "base_tools")
    monkeypatch.syspath_prepend(os.path.abspath(base_tools))
    # Purge cả bản package — WIKI_ROOT chốt ở import-time (cùng pattern
    # tests/test_reserved_index.py). "ingest" purge kèm để test Task 3 import
    # bản sạch với WIKI_ROOT trỏ vào tmp root.
    for mod in [m for m in list(sys.modules) if m in (
            "graph", "db", "search", "chunking", "config_file", "embed", "paths",
            "llm_wiki_base.paths", "llm_wiki_base.config_file", "ingest")]:
        del sys.modules[mod]
    import graph
    return graph


def test_extract_frontmatter_relations(tmp_path, monkeypatch):
    graph = _load_graph(tmp_path, monkeypatch)
    txt = (
        "---\n"
        "title: ba\n"
        "relations:\n"
        "  - rel: contrast-with\n"
        "    target: wiki/languages/grammar-point/ba.md\n"
        '    note: "điều kiện 〜たら"\n'
        "    source: s1\n"
        "---\n"
        "\n"
        "# ba\n"
    )
    links = graph.extract_links(txt)
    assert links == [graph.Link(
        rel="contrast-with",
        dst="wiki/languages/grammar-point/ba.md",
        note="điều kiện 〜たら",
        src_footnote="s1",
        origin="frontmatter",
    )]


def test_extract_frontmatter_japanese_note(tmp_path, monkeypatch):
    graph = _load_graph(tmp_path, monkeypatch)
    txt = (
        "---\n"
        "relations:\n"
        "  - rel: contrast-with\n"
        "    target: wiki/languages/grammar-point/ba.md\n"
        '    note: "〜たら — conditional clause"\n'
        "    source: s1\n"
        "---\n"
        "\n"
        "# ba\n"
    )
    links = graph.extract_links(txt)
    assert links == [graph.Link(
        rel="contrast-with",
        dst="wiki/languages/grammar-point/ba.md",
        note="〜たら — conditional clause",
        src_footnote="s1",
        origin="frontmatter",
    )]


def test_extract_inline_typed(tmp_path, monkeypatch):
    graph = _load_graph(tmp_path, monkeypatch)
    txt = (
        "# x\n"
        "\n"
        "[[wiki/x.md|rel:contrast-with]]\n"
        "\n"
        "Ví dụ: [[wiki/y.md|rel:example-of|Ví dụ]].\n"
    )
    links = graph.extract_links(txt)
    assert graph.Link(rel="contrast-with", dst="wiki/x.md",
                      note=None, src_footnote=None,
                      origin="inline") in links
    assert graph.Link(rel="example-of", dst="wiki/y.md",
                      note="Ví dụ", src_footnote=None,
                      origin="inline") in links
    assert len(links) == 2


def test_extract_plain_wikilink_default_rel(tmp_path, monkeypatch):
    graph = _load_graph(tmp_path, monkeypatch)
    bare = graph.extract_links("# x\n\n[[wiki/x.md]]\n")
    assert bare == [graph.Link(rel="related", dst="wiki/x.md",
                               note=None, src_footnote=None,
                               origin="wikilink")]
    aliased = graph.extract_links("# x\n\n[[wiki/x.md|alias text]]\n")
    assert aliased == [graph.Link(rel="related", dst="wiki/x.md",
                                  note="alias text", src_footnote=None,
                                  origin="wikilink")]


def test_dedup_frontmatter_wins(tmp_path, monkeypatch):
    graph = _load_graph(tmp_path, monkeypatch)
    txt = (
        "---\n"
        "relations:\n"
        "  - rel: contrast-with\n"
        "    target: wiki/x.md\n"
        '    note: "fm note"\n'
        "    source: s1\n"
        "---\n"
        "\n"
        "# x\n"
        "\n"
        "[[wiki/x.md|rel:contrast-with|inline note]]\n"
    )
    links = graph.extract_links(txt)
    assert len(links) == 1
    assert links[0].origin == "frontmatter"
    assert links[0].note == "fm note"
    assert links[0].src_footnote == "s1"


def test_extract_claim_anchor(tmp_path, monkeypatch):
    graph = _load_graph(tmp_path, monkeypatch)
    txt = (
        "# ba\n"
        "\n"
        "## Claims\n"
        "\n"
        "- claim text.[^s2] "
        "[[wiki/languages/grammar-point/ba.md#claims|rel:contradicts]]\n"
        "\n"
        "## Other\n"
        "\n"
        "[[wiki/y.md|rel:contradicts]]\n"
    )
    links = graph.extract_links(txt)
    assert graph.Link(
        rel="contradicts",
        dst="wiki/languages/grammar-point/ba.md#claims",
        note="claim text.",
        src_footnote=None,
        origin="inline",
    ) in links
    # Outside ## Claims: note stays None (inline typed handling).
    assert graph.Link(rel="contradicts", dst="wiki/y.md",
                      note=None, src_footnote=None,
                      origin="inline") in links
    assert len(links) == 2


def test_skip_fenced_code_blocks(tmp_path, monkeypatch):
    graph = _load_graph(tmp_path, monkeypatch)
    txt = (
        "# x\n"
        "\n"
        "```markdown\n"
        "[[wiki/fenced.md|rel:contrast-with]]\n"
        "[[wiki/fenced-plain.md]]\n"
        "```\n"
        "\n"
        "Real: [[wiki/real.md|rel:example-of]]\n"
        "\n"
        "## Claims\n"
        "\n"
        "```text\n"
        "- fake claim.[^s9] [[wiki/fake.md|rel:contradicts]]\n"
        "```\n"
        "\n"
        "- real claim.[^s2] "
        "[[wiki/real-claim.md#claims|rel:contradicts]]\n"
        "\n"
        "## Other\n"
    )
    links = graph.extract_links(txt)
    dsts = {l.dst for l in links}
    # Link trong fence → không trích (không phantom edge).
    assert "wiki/fenced.md" not in dsts
    assert "wiki/fenced-plain.md" not in dsts
    # Fence trong ## Claims → bullet + link trong đó không contribute.
    assert "wiki/fake.md" not in dsts
    # Link ngoài fence vẫn trích bình thường (test không pass vacuum).
    assert graph.Link(rel="example-of", dst="wiki/real.md",
                      note=None, src_footnote=None,
                      origin="inline") in links
    assert graph.Link(rel="contradicts", dst="wiki/real-claim.md#claims",
                      note="real claim.", src_footnote=None,
                      origin="inline") in links
    assert len(links) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Task 2: links table + sync_links (db.py)
# ─────────────────────────────────────────────────────────────────────────────


def test_sync_links_upserts(tmp_path, monkeypatch):
    _load_graph(tmp_path, monkeypatch)
    import db
    conn = db.get_conn(":memory:")
    db.init_db(conn)
    txt = (
        "---\n"
        "relations:\n"
        "  - rel: contrast-with\n"
        "    target: wiki/y.md\n"
        '    note: "điều kiện 〜たら"\n'
        "    source: s1\n"
        "---\n"
        "\n"
        "# x\n"
    )
    n = db.sync_links(conn, "wiki/a.md", txt)
    assert n == 1
    rows = db.get_links(conn, "wiki/a.md")
    assert len(rows) == 1
    row = rows[0]
    assert row["src"] == "wiki/a.md"
    assert row["rel"] == "contrast-with"
    assert row["dst"] == "wiki/y.md"
    assert row["note"] == "điều kiện 〜たら"
    assert row["src_footnote"] == "s1"
    assert row["origin"] == "frontmatter"


def test_sync_links_gcs_removed_edges(tmp_path, monkeypatch):
    _load_graph(tmp_path, monkeypatch)
    import db
    conn = db.get_conn(":memory:")
    db.init_db(conn)
    # Src khác — GC của wiki/a.md không được đụng tới.
    db.sync_links(conn, "wiki/other.md", "[[wiki/keep.md]]\n")
    # 2 edges: typed + default.
    n = db.sync_links(
        conn, "wiki/a.md",
        "# x\n\n"
        "[[wiki/a.md|rel:contrast-with]]\n"
        "[[wiki/b.md]]\n",
    )
    assert n == 2
    # Edit: chỉ còn 1 edge → edge typed bị GC.
    n2 = db.sync_links(
        conn, "wiki/a.md",
        "# x\n\n[[wiki/b.md]]\n",
    )
    assert n2 == 1
    rows = db.get_links(conn, "wiki/a.md")
    assert len(rows) == 1
    assert rows[0]["rel"] == "related"
    assert rows[0]["dst"] == "wiki/b.md"
    assert rows[0]["origin"] == "wikilink"
    # Src khác còn nguyên.
    assert len(db.get_links(conn, "wiki/other.md")) == 1


def test_links_table_in_init_db(tmp_path, monkeypatch):
    _load_graph(tmp_path, monkeypatch)
    import db
    conn = db.get_conn(":memory:")
    db.init_db(conn)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE name='links'"
    ).fetchone()
    assert row is not None
    assert row["name"] == "links"


# ─────────────────────────────────────────────────────────────────────────────
# Task 3: ingest CLI syncs links (ingest.py)
# ─────────────────────────────────────────────────────────────────────────────


def test_ingest_cli_syncs_links(tmp_path, monkeypatch, capsys):
    """ingest.py <page> để lại edge trong bảng links (WIKI_ROOT trỏ vào tmp)."""
    _load_graph(tmp_path, monkeypatch)  # env + purge (kèm "ingest") trước import
    # Vector tắt trong tmp config → không embedding (deterministic, offline).
    (tmp_path / ".llm-wiki-base.toml").write_text(
        "[retrieval]\nvector = false\n", encoding="utf-8"
    )
    # Page thật với frontmatter relation (typed relation — Task 1/2 format).
    page = tmp_path / "wiki" / "languages" / "grammar-point" / "ba.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\n"
        "title: ba\n"
        "relations:\n"
        "  - rel: contrast-with\n"
        "    target: wiki/languages/grammar-point/xu.md\n"
        '    note: "điều kiện 〜たら"\n'
        "    source: s1\n"
        "---\n"
        "\n"
        "# ba\n",
        encoding="utf-8",
    )
    import ingest

    monkeypatch.setattr(sys, "argv", ["ingest.py", str(page)])
    ingest.main()
    assert "indexed" in capsys.readouterr().out  # đường happy path, không skip

    # Cùng DB mà ingest vừa ghi (db.DB_PATH derive từ WIKI_ROOT=tmp).
    import db
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT src, rel, dst, note, src_footnote, origin FROM links"
        ).fetchall()
        page_row = conn.execute(
            "SELECT path FROM pages WHERE path = ?", ("wiki/languages/grammar-point/ba.md",)
        ).fetchone()
    finally:
        conn.close()
    assert page_row is not None  # page thực sự được index
    assert len(rows) == 1  # sync_links chạy sau index_file
    row = rows[0]
    assert row["src"] == "wiki/languages/grammar-point/ba.md"
    assert row["rel"] == "contrast-with"
    assert row["dst"] == "wiki/languages/grammar-point/xu.md"
    assert row["note"] == "điều kiện 〜たら"
    assert row["src_footnote"] == "s1"
    assert row["origin"] == "frontmatter"


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 fix: delete_page dọn cả links rows của src (reindex = reconcile step)
# ─────────────────────────────────────────────────────────────────────────────


def test_delete_page_removes_its_links(tmp_path, monkeypatch):
    """delete_page xoá edge của src — không để orphan links rows khi page biến mất."""
    _load_graph(tmp_path, monkeypatch)
    import db
    conn = db.get_conn(":memory:")
    db.init_db(conn)
    # Page "a" được index (có row pages) + có edge; page khác phải sống sót.
    db.upsert_page(conn, "wiki/a.md", "a", "t", "concept", "# a\n", 0.0)
    db.sync_links(conn, "wiki/a.md", "# a\n\n[[wiki/b.md]]\n")
    db.sync_links(conn, "wiki/other.md", "[[wiki/keep.md]]\n")
    # Orphan case: links tồn tại nhưng row pages đã không còn từ lần chạy trước.
    db.sync_links(conn, "wiki/ghost.md", "[[wiki/gone.md]]\n")

    db.delete_page(conn, "wiki/a.md")
    db.delete_page(conn, "wiki/ghost.md")

    assert db.get_links(conn, "wiki/a.md") == []
    # Kể cả khi row pages đã biến mất, links của src vẫn được dọn.
    assert db.get_links(conn, "wiki/ghost.md") == []
    # Src khác không bị đụng tới.
    other = db.get_links(conn, "wiki/other.md")
    assert len(other) == 1
    assert other[0]["src"] == "wiki/other.md"
    assert other[0]["dst"] == "wiki/keep.md"


# ─────────────────────────────────────────────────────────────────────────────
# Task 4: language pack loading + pack-aware validation (opt-in [langpack])
# ─────────────────────────────────────────────────────────────────────────────


def _japanese_pack(tmp_path, monkeypatch):
    """Wiki tmp bật `[langpack] japanese` → pack dict THẬT từ templates/."""
    graph = _load_graph(tmp_path, monkeypatch)
    (tmp_path / ".llm-wiki-base.toml").write_text(
        '[langpack]\nenabled = true\npack = "japanese"\n', encoding="utf-8"
    )
    pack = graph.load_langpack(str(tmp_path))
    assert pack is not None
    return graph, pack


def test_load_langpack_disabled_returns_none(tmp_path, monkeypatch):
    """TOML thiếu [langpack] / enabled=false / pack rỗng → None (zero change)."""
    graph = _load_graph(tmp_path, monkeypatch)
    # Không có toml → None.
    assert graph.load_langpack(str(tmp_path)) is None
    # Có toml nhưng thiếu [langpack] → None.
    (tmp_path / ".llm-wiki-base.toml").write_text(
        '[wiki]\nprofile = "personal"\n', encoding="utf-8"
    )
    assert graph.load_langpack(str(tmp_path)) is None
    # enabled=false → None.
    (tmp_path / ".llm-wiki-base.toml").write_text(
        '[langpack]\nenabled = false\npack = "japanese"\n', encoding="utf-8"
    )
    assert graph.load_langpack(str(tmp_path)) is None
    # enabled=true nhưng pack rỗng → None.
    (tmp_path / ".llm-wiki-base.toml").write_text(
        '[langpack]\nenabled = true\npack = ""\n', encoding="utf-8"
    )
    assert graph.load_langpack(str(tmp_path)) is None


def test_load_langpack_japanese(tmp_path, monkeypatch):
    """Pack japanese load được kinds + relations từ templates/langpacks/."""
    graph, pack = _japanese_pack(tmp_path, monkeypatch)
    assert pack["name"] == "japanese"
    assert "grammar-point" in pack["kinds"]
    assert "vocab" in pack["kinds"]
    assert "contrast-with" in pack["relations"]
    assert "covered-in" in pack["relations"]
    # Ràng buộc targets của covered-in parse đúng từ relations.yml.
    assert pack["relations"]["covered-in"] == {"targets": ["source"]}


def test_validate_unknown_rel(tmp_path, monkeypatch):
    """Rel lạ → unknown-rel-type; DEFAULT_REL 'related' luôn được phép."""
    graph, pack = _japanese_pack(tmp_path, monkeypatch)
    links = [
        graph.Link(rel="vague-rel", dst="wiki/x.md", note=None,
                   src_footnote=None, origin="wikilink"),
        graph.Link(rel="related", dst="wiki/y.md", note=None,
                   src_footnote=None, origin="wikilink"),
    ]
    errors = graph.validate_links(links, pack)
    assert len(errors) == 1  # chỉ rel lạ; related không lỗi
    assert "unknown-rel-type" in errors[0]
    assert "vague-rel" in errors[0]
    # related LUÔN hợp lệ, kể cả khi pack không khai entry riêng.
    bare = {"name": "bare", "kinds": {}, "relations": {}}
    assert graph.validate_links(
        [graph.Link(rel="related", dst="wiki/y.md", note=None,
                    src_footnote=None, origin="wikilink")],
        bare,
    ) == []


def test_validate_targets_constraint(tmp_path, monkeypatch):
    """covered-in (targets=[source]) chỉ nhận dst là .../source/... path."""
    graph, pack = _japanese_pack(tmp_path, monkeypatch)
    bad = graph.Link(rel="covered-in", dst="wiki/languages/concept/x.md",
                     note=None, src_footnote=None, origin="frontmatter")
    good = graph.Link(rel="covered-in", dst="wiki/languages/source/x.md",
                      note=None, src_footnote=None, origin="frontmatter")
    errors = graph.validate_links([bad], pack)
    assert len(errors) == 1
    assert "covered-in" in errors[0]
    assert graph.validate_links([good], pack) == []


def test_validate_no_pack_passthrough(tmp_path, monkeypatch):
    """pack=None → [] luôn: wiki không langpack không bị validate (regression)."""
    graph = _load_graph(tmp_path, monkeypatch)
    links = [
        graph.Link(rel="vague-rel", dst="wiki/x.md", note=None,
                   src_footnote=None, origin="wikilink"),
        graph.Link(rel="covered-in", dst="wiki/languages/concept/x.md",
                   note=None, src_footnote=None, origin="frontmatter"),
        graph.Link(rel="contradicts",
                   dst="wiki/languages/grammar-point/ba.md#claims",
                   note="claim.", src_footnote=None, origin="inline"),
    ]
    assert graph.validate_links(links, None) == []
