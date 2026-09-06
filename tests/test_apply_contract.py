"""P1: proposals apply output contract — JSON first, APPLIED\\t fallback."""


def test_parse_json_result_line():
    from llm_wiki.cli import parse_apply_output
    out = "APPLIED\twiki/tech/kind/x.md\n✓ applied → wiki/tech/kind/x.md\nRESULT {\"status\": \"applied\", \"target\": \"wiki/tech/kind/x.md\"}\n"
    assert parse_apply_output(out, None) == "wiki/tech/kind/x.md"


def test_parse_legacy_applied_tab_fallback():
    from llm_wiki.cli import parse_apply_output
    out = "APPLIED\twiki/tech/kind/x.md\n✓ applied → wiki/tech/kind/x.md (sửa), đã xoá proposal\n"
    assert parse_apply_output(out, None) == "wiki/tech/kind/x.md"


def test_parse_unreadable_returns_none():
    from llm_wiki.cli import parse_apply_output
    assert parse_apply_output("some unrelated output\n", None) is None


def test_explicit_target_wins():
    from llm_wiki.cli import parse_apply_output
    out = "RESULT {\"status\": \"applied\", \"target\": \"wiki/a.md\"}\n"
    assert parse_apply_output(out, "wiki/b.md") == "wiki/b.md"
