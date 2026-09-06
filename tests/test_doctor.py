"""doctor PATH check: warn when `llm-wiki` is not on PATH."""


def test_doctor_warns_when_not_on_path(tmp_path, monkeypatch, runner):
    monkeypatch.setenv("PATH", str(tmp_path))
    from llm_wiki.cli import app
    result = runner.invoke(app, ["setup", "doctor", "--root", str(tmp_path)])
    assert result.exit_code in (0, 1)
    assert "not on PATH" in result.output
