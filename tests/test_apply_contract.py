"""P1: proposals apply output contract — JSON first, APPLIED\\t fallback."""


def test_parse_json_result_line():
    from llm_wiki_base.cli import parse_apply_output
    out = "APPLIED\twiki/tech/kind/x.md\n✓ applied → wiki/tech/kind/x.md\nRESULT {\"status\": \"applied\", \"target\": \"wiki/tech/kind/x.md\"}\n"
    assert parse_apply_output(out, None) == "wiki/tech/kind/x.md"


def test_parse_legacy_applied_tab_fallback():
    from llm_wiki_base.cli import parse_apply_output
    out = "APPLIED\twiki/tech/kind/x.md\n✓ applied → wiki/tech/kind/x.md (sửa), đã xoá proposal\n"
    assert parse_apply_output(out, None) == "wiki/tech/kind/x.md"


def test_parse_unreadable_returns_none():
    from llm_wiki_base.cli import parse_apply_output
    assert parse_apply_output("some unrelated output\n", None) is None


def test_explicit_target_wins():
    from llm_wiki_base.cli import parse_apply_output
    out = "RESULT {\"status\": \"applied\", \"target\": \"wiki/a.md\"}\n"
    assert parse_apply_output(out, "wiki/b.md") == "wiki/b.md"


def _load_proposals(tmp_path, monkeypatch):
    import os
    import sys
    monkeypatch.setenv("WIKI_ROOT", str(tmp_path))
    monkeypatch.setenv("WIKI_DB", str(tmp_path / "wiki" / ".wiki.db"))
    monkeypatch.syspath_prepend(os.path.abspath(os.path.join("src", "llm_wiki_base", "base_tools")))
    for mod in [m for m in list(sys.modules)
                if m in ("db", "search", "chunking", "config_file", "embed", "paths", "proposals")]:
        del sys.modules[mod]
    import proposals
    return proposals


def test_apply_emits_json_and_cli_roundtrips(tmp_path, monkeypatch, capsys):
    """End-to-end: stage → apply → output chứa cả APPLIED + RESULT JSON hợp lệ,
    và parser của CLI đọc lại đúng target thật trên đĩa."""
    import json
    from types import SimpleNamespace
    proposals = _load_proposals(tmp_path, monkeypatch)
    (tmp_path / "wiki").mkdir(parents=True, exist_ok=True)

    body = "# x\n\n" + "concept content " * 20
    prop = proposals.stage(tmp_path, "wiki/tech/concept/x.md", body, by="t", note="")
    rc = proposals.cmd_apply(SimpleNamespace(name=prop.name, target=None))
    out = capsys.readouterr().out

    assert rc == 0
    dest = tmp_path / "wiki" / "tech" / "concept" / "x.md"
    assert dest.read_text(encoding="utf-8") == body
    assert not prop.exists()
    assert "APPLIED\twiki/tech/concept/x.md" in out
    result_line = next(ln for ln in out.splitlines() if ln.startswith("RESULT "))
    payload = json.loads(result_line[len("RESULT "):])
    assert payload == {"status": "applied", "target": "wiki/tech/concept/x.md"}

    from llm_wiki_base.cli import parse_apply_output
    assert parse_apply_output(out, None) == "wiki/tech/concept/x.md"
