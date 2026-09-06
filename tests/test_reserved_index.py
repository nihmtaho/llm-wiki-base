"""P1: reserved pages (log.md/index.md) must not enter page-level BM25."""
import os
import sys


def _load_base_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_path))
    base_tools = os.path.join("src", "llm_wiki", "base_tools")
    monkeypatch.syspath_prepend(os.path.abspath(base_tools))
    for mod in [m for m in list(sys.modules) if m in (
            "db", "search", "chunking", "config_file", "embed", "paths",
            "llm_wiki.paths", "llm_wiki.config_file")]:
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


def _load_module(tmp_path, monkeypatch, name, stub_rag=False):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_path))
    base_tools = os.path.join("src", "llm_wiki", "base_tools")
    monkeypatch.syspath_prepend(os.path.abspath(base_tools))
    # paths phải purge cả bản package (llm_wiki.paths) — WIKI_ROOT chốt ở import-time,
    # bản base_tools/paths.py chỉ re-export nó khi package cài được.
    for mod in [m for m in list(sys.modules) if m in (
            "db", "search", "chunking", "config_file", "embed", "paths",
            "llm_wiki.paths", "llm_wiki.config_file",
            "reindex", "ingest", "index")]:
        del sys.modules[mod]
    if stub_rag:
        import types
        stub = types.ModuleType("index")
        stub.build_index = lambda **kw: 0
        monkeypatch.setitem(sys.modules, "index", stub)
    return __import__(name)


def test_reindex_collect_skips_reserved(tmp_path, monkeypatch):
    """reindex không thu gom reserved → row cũ thành stale và bị db.delete_page dọn."""
    reindex = _load_module(tmp_path, monkeypatch, "reindex", stub_rag=True)
    try:
        (tmp_path / "wiki" / "tech").mkdir(parents=True, exist_ok=True)
        (tmp_path / "wiki" / "log.md").write_text("# log\n", encoding="utf-8")
        (tmp_path / "wiki" / "index.md").write_text("# index\n", encoding="utf-8")
        (tmp_path / "wiki" / "tech" / "a.md").write_text("# a\n", encoding="utf-8")
        rels = [rel for rel, _fp in reindex._collect_files()]
        assert "wiki/tech/a.md" in rels
        assert "wiki/log.md" not in rels
        assert "wiki/index.md" not in rels
    finally:
        # reindex chèn global rag dir vào sys.path ở import-time — dọn để không
        # làm bẩn các test khác (monkeypatch không revert việc này).
        global_rag = os.path.join(
            os.environ.get("LLM_WIKI_BASE_DIR", os.path.expanduser("~/.llm-wiki-base")), "rag")
        while global_rag in sys.path:
            sys.path.remove(global_rag)


def test_ingest_skips_reserved(tmp_path, monkeypatch, capsys):
    """ingest wiki/log.md → exit 0 kèm 'skip', không chạm DB."""
    ingest = _load_module(tmp_path, monkeypatch, "ingest")
    (tmp_path / "wiki").mkdir(parents=True, exist_ok=True)
    target = tmp_path / "wiki" / "log.md"
    target.write_text("# log\n\n" + "h " * 100, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["ingest.py", str(target)])
    import pytest
    with pytest.raises(SystemExit) as exc:
        ingest.main()
    assert exc.value.code == 0
    assert "skip" in capsys.readouterr().out
