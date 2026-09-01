"""llm-wiki CLI — Typer app.

Subcommands:
    base install    — install global runtime to ~/.llm-wiki-base/ (1 lần per máy)
    base path       — print current base dir
    init personal   — init personal knowledge wiki in-place (data only)
    init project    — init project wiki + install MCP globally + link skills
    ingest          — wrapper: gọi global tools/ingest.py với cwd context
    reindex         — wrapper: rebuild search DB + RAG
    lint            — wrapper: health check
    watch           — wrapper: daemon scan inbox + ingest + reindex
    translate add   — dịch wiki pages sang ngôn ngữ khác
    translate check — verify bản dịch đồng bộ với source
"""
import os
import subprocess
from pathlib import Path

import typer
from rich.console import Console

from llm_wiki import __version__
from llm_wiki.base import get_base_dir, get_base_python, install_base

app = typer.Typer(
    name="llm-wiki",
    help="LLM-maintained wiki với hybrid BM25+vector search, MCP bridge, multi-base init.",
    no_args_is_help=True,
    add_completion=False,
)

init_app = typer.Typer(help="Init mới 1 wiki (personal hoặc project)")
app.add_typer(init_app, name="init")

base_app = typer.Typer(help="Manage global llm-wiki-base runtime (~/.llm-wiki-base/)")
app.add_typer(base_app, name="base")

translate_app = typer.Typer(help="Translate wiki pages sang ngôn ngữ khác")
app.add_typer(translate_app, name="translate")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"llm-wiki {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V",
        callback=_version_callback,
        is_eager=True,
        help="Print version và exit.",
    ),
) -> None:
    """llm-wiki CLI — root callback (chỉ để register --version)."""


@init_app.command("personal")
def init_personal(
    here: bool = typer.Option(True, "--here", help="Init tại cwd (in-place)."),
    name: str | None = typer.Option(None, "--name", "-n", help="Wiki name (default: tên folder)."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirm nếu dir có content."),
    skills_target: str = typer.Option(
        "universal", "--skills-target",
        help="Skill install location: 'universal' (<wiki>/.agents/skills/), 'claude' (chỉ .claude/skills/ + symlink), 'both' (copy cả 2).",
    ),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip skill install."),
) -> None:
    """Init 1 personal knowledge wiki tại cwd. In-place."""
    from llm_wiki.init_personal import run
    cwd = Path.cwd()
    target = "skip" if no_skills else skills_target
    run(cwd=cwd, name=name, force=force, skills_target=target)


@init_app.command("project")
def init_project(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root (default: cwd)."),
    wiki_dir: str = typer.Option(
        "project-wiki", "--wiki-dir", "-w",
        help="Subfolder dưới project root để chứa wiki data.",
    ),
    client: list[str] = typer.Option(
        ["claude"], "--client", "-c",
        help="AI client để install MCP. Có thể truyền nhiều lần: -c claude -c opencode.",
    ),
    server_name: str = typer.Option(
        "llm-wiki-mcp", "--server-name", "-s",
        help="Tên MCP server (đổi nếu conflict với project khác trên cùng máy).",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirm nếu wiki subdir có content."),
    skills_target: str = typer.Option(
        "universal", "--skills-target",
        help="Skill install location: 'universal' (<wiki>/.agents/skills/), 'claude' (chỉ .claude/skills/ + symlink), 'both' (copy cả 2).",
    ),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip skill install."),
) -> None:
    """Init project wiki: tạo <root>/<wiki-dir>/ + cài MCP globally + copy skills per-wiki."""
    from llm_wiki.init_project import run
    target = "skip" if no_skills else skills_target
    run(
        root=root,
        wiki_subdir=wiki_dir,
        clients=client,
        server_name=server_name,
        force=force,
        skills_target=target,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Global base (runtime) management
# ─────────────────────────────────────────────────────────────────────────────


@base_app.command("install")
def base_install(
    dir: Path = typer.Option(
        None, "--dir", "-d",
        help="Target dir (default: ~/.llm-wiki-base). Có thể override qua env LLM_WIKI_BASE_DIR.",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Recreate venv + reinstall requirements."),
) -> None:
    """Install global llm-wiki-base runtime (tools/, rag/, scripts/, .venv/).

    Chạy 1 lần sau khi `pip install llm-wiki`. Idempotent — chạy lại để sync
    tools/rag/scripts mới nhất từ package.
    """
    base = install_base(base_dir=dir, force=force)
    console.print(f"[green]✓[/green] llm-wiki-base installed at: {base}")
    console.print(f"  python: {get_base_python()}")
    console.print()
    console.print("Next: cd vào 1 folder trống rồi `llm-wiki init personal` để tạo wiki data.")


@base_app.command("path")
def base_path() -> None:
    """In đường dẫn global base hiện tại (env override hoặc default)."""
    console.print(get_base_dir())


# ─────────────────────────────────────────────────────────────────────────────
# Per-wiki wrappers (gọi global tools/ với cwd context)
# ─────────────────────────────────────────────────────────────────────────────


def _run_base_tool(tool_name: str, args: list[str], wiki_root: Path) -> None:
    """Run 1 script trong global base với cwd context của wiki."""
    base = get_base_dir()
    py = get_base_python()
    script = base / "tools" / tool_name
    if not script.exists():
        console.print(f"[red]Error:[/red] {script} không tồn tại.")
        console.print(f"  Chạy [cyan]llm-wiki base install[/cyan] trước.")
        raise SystemExit(1)
    # Set WIKI_ROOT = absolute path of wiki, inherit other env
    env = os.environ.copy()
    env["WIKI_ROOT"] = str(wiki_root.resolve())
    subprocess.check_call([str(py), str(script), *args], cwd=str(wiki_root), env=env)


@app.command("ingest")
def ingest_cmd(
    path: str = typer.Argument(..., help="Source path relative to wiki root (vd: raw/inbox/foo.md)."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Ingest 1 source vào search DB. Chạy từ trong wiki dir."""
    target = Path(path)
    abs_target = target if target.is_absolute() else (root / target)
    _run_base_tool("ingest.py", [str(abs_target)], root)


@app.command("reindex")
def reindex_cmd(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Rebuild search DB + RAG index cho toàn bộ wiki."""
    _run_base_tool("reindex.py", [], root)


@app.command("lint")
def lint_cmd(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Health-check wiki: orphan, broken link, missing file, stale claim."""
    _run_base_tool("lint.py", ["--root", str(root)], root)


@app.command("watch")
def watch_cmd(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Daemon: scan raw/inbox/ → ingest → reindex → lint. Chạy từ trong wiki dir."""
    _run_base_tool("watch.py", [], root)


@translate_app.command("enable")
def translate_enable(
    lang: list[str] = typer.Option(
        ..., "--lang", "-l",
        help="Target language code (vd: vi, ja, fr). Có thể truyền nhiều lần: -l vi -l ja.",
    ),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd).",
    ),
) -> None:
    """Enable auto-translation. Ghi target langs vào `.llm-wiki.toml` ở wiki root.

    Sau khi enable, ingest skill sẽ tự gọi `llm-wiki-translate` skill để dịch mỗi
    source mới sang các target langs (dùng LLM của AI tool đang chạy).
    """
    from llm_wiki.config_file import set_translate
    p = set_translate(root, enabled=True, langs=lang)
    console.print(f"[green]✓[/green] enabled → {', '.join(sorted(set(lang)))}")
    console.print(f"  ghi vào: {p}")
    console.print()
    console.print("Ingest từ giờ sẽ tự tạo <slug>.<lang>.md cho mỗi page mới.")
    console.print("Bản dịch KHÔNG vào DB/RAG (skip rule *.lang.md).")


@translate_app.command("disable")
def translate_disable(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd).",
    ),
) -> None:
    """Disable auto-translation. Giữ list langs để enable lại sau."""
    from llm_wiki.config_file import get_translate_config, set_translate
    _, langs = get_translate_config(root)
    set_translate(root, enabled=False, langs=langs)
    if langs:
        console.print(f"[green]✓[/green] disabled (langs vẫn lưu: {langs}). Dùng `llm-wiki translate enable` để bật lại.")
    else:
        console.print("[green]✓[/green] disabled.")


@translate_app.command("status")
def translate_status(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd).",
    ),
) -> None:
    """In trạng thái auto-translation hiện tại."""
    from llm_wiki.config_file import get_translate_config
    enabled, langs = get_translate_config(root)
    status = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
    console.print(f"auto-translate: {status}")
    console.print(f"target langs:   {langs if langs else '(empty)'}")


@translate_app.command("check")
def translate_check(
    lang: str = typer.Option(..., "--lang", "-l", help="Language code cần verify."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd).",
    ),
) -> None:
    """Verify mỗi <slug>.md có matching <slug>.<lang>.md với cùng frontmatter keys + heading structure.

    Không cần LLM — chỉ đọc file + so sánh structure.
    """
    from llm_wiki.translate import run_check
    code = run_check(wiki_root=root, lang=lang)
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
