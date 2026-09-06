"""P1: reserved pages (log.md/index.md) must not enter page-level BM25."""
import os
import sys


def _load_base_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_path))
    base_tools = os.path.join("src", "llm_wiki", "base_tools")
    monkeypatch.syspath_prepend(os.path.abspath(base_tools))
    for mod in [m for m in list(sys.modules) if m in (
            "db", "search", "chunking", "config_file", "embed", "paths")]:
        del sys.modules[mod]
    import db
    import search
    return db, search


def test_reserved_log_not_indexed(tmp_path, monkeypatch):
    db, search = _load_base_tools(tmp_path, monkeypatch)
    conn = db.get_conn(":memory:")
    db.init_db(conn)
    marker = "zkwreservedmarkerqzx"
    search.index_file(conn, "wiki/log.md", "log", "", "",
                      f"# log\n\n{marker} history entry\n\n" + "x " * 100)
    search.index_file(conn, "wiki/tech/concept/x.md", "x", "tech", "concept",
                      f"# x\n\n{marker} real concept\n\n" + "y " * 100)
    paths = [r["path"] for r in conn.execute("SELECT path FROM pages").fetchall()]
    assert "wiki/tech/concept/x.md" in paths
    assert "wiki/log.md" not in paths


def test_reserved_index_not_indexed(tmp_path, monkeypatch):
    db, search = _load_base_tools(tmp_path, monkeypatch)
    conn = db.get_conn(":memory:")
    db.init_db(conn)
    search.index_file(conn, "wiki/index.md", "index", "", "",
                      "# index\n\n" + "z " * 100)
    paths = [r["path"] for r in conn.execute("SELECT path FROM pages").fetchall()]
    assert "wiki/index.md" not in paths
