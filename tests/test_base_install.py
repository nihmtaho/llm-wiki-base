"""install_base phải mang templates/langpacks/ về global base.

graph._langpack_candidates resolve `dirname(dirname(graph.__file__))` → khi deploy,
tools/graph.py nằm ở <base>/tools/ nên pack phải về <base>/templates/langpacks/,
không thì wiki bật [langpack] sẽ FileNotFoundError (Task 4 concern #1).
"""
import sys
from pathlib import Path

from llm_wiki_base import base as base_mod
from llm_wiki_base._package_data import package_path

JAPANESE_FILES = ("kinds.yml", "relations.yml", "schema-notes.md")


def _stub_venv(base_mod, monkeypatch):
    """install_base phần venv/pip — không tạo venv thật trong test (offline, nhanh)."""
    monkeypatch.setattr(base_mod, "ensure_venv",
                        lambda b, force=False: Path(sys.executable))
    monkeypatch.setattr(base_mod.subprocess, "check_call",
                        lambda *a, **k: None)


def test_install_base_copies_langpacks(isolated_env, monkeypatch):
    _stub_venv(base_mod, monkeypatch)
    base_mod.install_base()

    base = isolated_env["base"]
    # Cả 3 file của pack japanese về đúng chỗ load_langpack sẽ tìm.
    for name in JAPANESE_FILES:
        dst = base / "templates" / "langpacks" / "japanese" / name
        assert dst.is_file(), f"thiếu {dst}"
        src = package_path("templates", "langpacks", "japanese", name)
        assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
    # Hành vi copy cũ không đổi (eval-golden vẫn về templates/).
    assert (base / "templates" / "eval-golden.toml").is_file()
    # tools/ sync kèm — điều kiện để dirname(dirname(graph.__file__)) trỏ về base.
    assert (base / "tools" / "graph.py").is_file()
