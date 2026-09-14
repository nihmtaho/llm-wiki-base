import os

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


@pytest.fixture()
def machine(isolated_env, tmp_path, monkeypatch):
    """Define exactly which AI clients 'this machine' has.

    Detection reads PATH for binaries, $HOME for config dirs and /Applications
    for app bundles. The first two are already isolated by `isolated_env`; the
    third is a module constant, so point it at an empty dir — otherwise a test
    run on a Mac with Zed installed would "detect" clients the fixture never
    gave it. `apps=` seeds that fake bundle root.
    """
    from llm_wiki_base import clients as _probe

    def _fake(*binaries: str, apps: tuple[str, ...] = ()):
        bin_dir = isolated_env["base"] / "bin"
        bin_dir.mkdir(exist_ok=True)
        for name in binaries:
            exe = bin_dir / (name + (".exe" if os.name == "nt" else ""))
            exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            exe.chmod(0o755)
        monkeypatch.setenv("PATH", str(bin_dir))

        root = tmp_path / "Applications"
        root.mkdir(exist_ok=True)
        for bundle in apps:
            (root / f"{bundle}.app").mkdir(exist_ok=True)
        monkeypatch.setattr(_probe, "APPS_ROOT", root)
        return bin_dir
    return _fake


@pytest.fixture(autouse=True)
def _restore_ui_state():
    yield
    _ui.set_quiet(False)
    _ui.set_no_color(False)
    _ui.set_debug(False)
