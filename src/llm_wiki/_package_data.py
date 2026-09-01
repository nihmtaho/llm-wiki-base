"""Helpers to load bundled package data (templates, skills) from wheel install.

Khi cài qua `pip install .`, files trong `src/llm_wiki/{templates,skills}/` được
ship trong wheel và accessible qua `importlib.resources`. Khi chạy từ source
(`pip install -e .` hoặc PYTHONPATH=src), load trực tiếp từ filesystem.
"""
from importlib import resources
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent


def package_path(*parts: str) -> Path:
    """Trả Path tới file/folder trong package data.

    Args:
        parts: path segments relative to package root, vd ("templates", "personal", "wiki-index.md")
    """
    return _PACKAGE_ROOT.joinpath(*parts)


def read_template(*parts: str) -> str:
    """Đọc content của 1 template/skill file trong package data."""
    return package_path(*parts).read_text(encoding="utf-8")


def template_exists(*parts: str) -> bool:
    """Check file/folder tồn tại trong package data."""
    return package_path(*parts).exists()
