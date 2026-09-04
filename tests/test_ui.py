from llm_wiki import _ui


def test_ok_panel_quiet_prints_facts_only(capsys):
    _ui.set_quiet(True)
    try:
        _ui.ok_panel("Wiki ready", ["name: demo"], ["llm-wiki wiki add demo"])
    finally:
        _ui.set_quiet(False)
    out = capsys.readouterr().out
    assert "name: demo" in out
    assert "Wiki ready" not in out
    assert "╭" not in out and "╮" not in out
