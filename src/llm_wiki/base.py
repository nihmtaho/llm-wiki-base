"""Global llm-wiki-base runtime: install + path resolution.

`llm-wiki-base` là global runtime directory chứa:
- `tools/`, `rag/`, `scripts/` — Python pipeline (share giữa các wikis).
- `.venv/` — 1 venv duy nhất cho mọi wikis.
- `requirements.txt` — pinned deps.

Per-wiki data (raw/, wiki/, rag_index/) KHÔNG nằm ở đây — mỗi wiki có data riêng
trong folder riêng, runtime base chỉ chứa code + env.

Default location: `~/.llm-wiki-base/`. Override qua env `LLM_WIKI_BASE_DIR`
(khi user muốn share runtime qua NFS, dùng prefix khác, v.v.).
"""
import os
import shutil
import subprocess
from pathlib import Path

from llm_wiki._package_data import package_path
from llm_wiki._venv import ensure_venv, venv_bin

DEFAULT_BASE_DIR: Path = Path.home() / ".llm-wiki-base"
BASE_DIR_ENV = "LLM_WIKI_BASE_DIR"


def get_base_dir() -> Path:
    """Resolve global base dir: env override > default ~/.llm-wiki-base."""
    val = os.environ.get(BASE_DIR_ENV)
    if val:
        return Path(val).expanduser().resolve()
    return DEFAULT_BASE_DIR


def install_base(base_dir: Path | None = None, force: bool = False) -> Path:
    """Install/sync global llm-wiki-base runtime to base_dir.

    Idempotent: re-running updates tools/rag/scripts/requirements in place;
    venv chỉ tạo nếu chưa có (hoặc nếu `force=True`).

    Args:
        base_dir: target dir. None = use `get_base_dir()`.
        force: nếu True, recreate venv + reinstall requirements.

    Returns:
        base_dir (resolved Path).
    """
    base = (base_dir or get_base_dir()).resolve()
    base.mkdir(parents=True, exist_ok=True)

    # 1. Copy tools/, rag/, scripts/ từ package data
    for sub in ["base_tools", "base_rag", "base_scripts"]:
        src = package_path(sub)
        if src.is_dir():
            _copy_tree_filtered(
                src,
                base / sub.replace("base_", ""),
                exclude={".venv", "__pycache__", ".rag_index", ".wiki.db", ".proposals"},
            )

    # 2. Copy requirements.txt
    req_src = package_path("requirements.txt")
    if req_src.exists():
        (base / "requirements.txt").write_text(
            req_src.read_text(encoding="utf-8"), encoding="utf-8"
        )

    # 3. Create / reuse venv + pip install
    py_bin = ensure_venv(base, force=force)
    req = base / "requirements.txt"
    if req.exists():
        subprocess.check_call(
            [str(py_bin), "-m", "pip", "install", "--quiet", "-r", str(req)],
            stdout=subprocess.DEVNULL,
        )

    return base


def _copy_tree_filtered(src: Path, dst: Path, exclude: set[str]) -> None:
    """Copy directory tree, bỏ entry match exclude (name hoặc path prefix)."""
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        rel = entry.relative_to(src)
        rel_str = str(rel)
        if rel_str in exclude or any(rel_str.startswith(e) for e in exclude):
            continue
        target = dst / rel
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)


def get_base_python() -> Path:
    """Trả path tới Python binary trong global venv."""
    return venv_bin(get_base_dir() / ".venv")
