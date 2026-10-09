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
