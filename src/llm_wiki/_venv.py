"""Helpers to create venv + install requirements for an inited wiki or global base."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def ensure_venv(target: Path, requirements: list[str] | None = None, force: bool = False) -> Path:
    """Tạo `.venv` tại target nếu chưa có, pip install requirements.

    Args:
        target: dir chứa .venv.
        requirements: list pip packages. None = không pip install (chỉ tạo venv).
        force: nếu True, xoá .venv cũ + tạo lại + reinstall.

    Returns path tới python binary trong venv (`<target>/.venv/bin/python` hoặc
    `<target>/.venv/Scripts/python.exe` trên Windows).
    """
    venv_dir = target / ".venv"
    py_bin = venv_bin(venv_dir)

    if force and venv_dir.exists():
        shutil.rmtree(venv_dir)

    if not venv_dir.exists():
        subprocess.check_call(
            [sys.executable, "-m", "venv", str(venv_dir)],
            stdout=subprocess.DEVNULL,
        )

    # Install requirements (skip if already satisfied — pip no-op)
    if requirements:
        subprocess.check_call(
            [str(py_bin), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
            stdout=subprocess.DEVNULL,
        )
        subprocess.check_call(
            [str(py_bin), "-m", "pip", "install", "--quiet", *requirements],
            stdout=subprocess.DEVNULL,
        )

    return py_bin


def venv_bin(venv_dir: Path) -> Path:
    """Trả path tới python binary trong venv (cross-platform)."""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def copy_directory_filtered(src: Path, dst: Path, exclude: set[str] | None = None) -> None:
    """Copy directory tree, bỏ các entry trong exclude (relative names hoặc path prefixes)."""
    exclude = exclude or set()
    dst.mkdir(parents=True, exist_ok=True)
    for src_entry in src.iterdir():
        rel = src_entry.relative_to(src)
        rel_str = str(rel)
        if rel_str in exclude or any(rel_str.startswith(e) for e in exclude):
            continue
        if src_entry.is_dir():
            shutil.copytree(src_entry, dst / rel, dirs_exist_ok=True)
        else:
            (dst / rel).write_bytes(src_entry.read_bytes())
