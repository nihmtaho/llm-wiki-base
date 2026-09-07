import pytest
from typer.testing import CliRunner

from llm_wiki_base import _ui


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    """Point base dir + HOME at tmp so tests never touch real state."""
    base = tmp_path / "base"
    home = tmp_path / "home"
    base.mkdir()
    home.mkdir()
    monkeypatch.setenv("LLM_WIKI_BASE_DIR", str(base))
    monkeypatch.setenv("HOME", str(home))
    return {"base": base, "home": home}


@pytest.fixture(autouse=True)
def _restore_ui_state():
    yield
    _ui.set_quiet(False)
    _ui.set_no_color(False)
    _ui.set_debug(False)
