"""Task 1: graph.py — pure, deterministic typed-relation link extraction."""
import os
import sys


def _load_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_path))
    base_tools = os.path.join("src", "llm_wiki_base", "base_tools")
    monkeypatch.syspath_prepend(os.path.abspath(base_tools))
    # Purge cả bản package — WIKI_ROOT chốt ở import-time (cùng pattern
    # tests/test_reserved_index.py).
    for mod in [m for m in list(sys.modules) if m in (
            "graph", "db", "search", "chunking", "config_file", "embed", "paths",
            "llm_wiki_base.paths", "llm_wiki_base.config_file")]:
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
