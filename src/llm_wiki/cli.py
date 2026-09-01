"""llm-wiki CLI — Typer app.

Subcommands:
    base install    — install global runtime to ~/.llm-wiki-base/ (1 lần per máy)
    base path       — print current base dir
    init            — interactive init wizard (personal hoặc project)
    init personal   — init personal knowledge wiki in-place (data only + MCP + registry)
    init project    — init project wiki + install centralized MCP globally + register
    wiki list       — list all registered wikis (TOML registry)
    wiki add        — register a wiki manually
    wiki remove     — unregister a wiki
    ingest          — wrapper: gọi global tools/ingest.py với cwd context
    reindex         — wrapper: rebuild search DB + RAG
    lint            — wrapper: health check
    watch           — wrapper: daemon scan inbox + ingest + reindex
    translate add   — dịch wiki pages sang ngôn ngữ khác
    translate check — verify bản dịch đồng bộ với source
    config show     — in effective config (defaults + .llm-wiki.toml + env override)
    verify          — human duyệt artifact: set/clear `verified` trong frontmatter page
"""
import os
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt

from llm_wiki import __version__
from llm_wiki.base import get_base_dir, get_base_python, install_base

app = typer.Typer(
    name="llm-wiki",
    help="LLM-maintained wiki với hybrid BM25+vector search, centralized MCP bridge, multi-base init.",
    no_args_is_help=True,
    add_completion=False,
)

init_app = typer.Typer(help="Init mới 1 wiki (personal hoặc project)")
app.add_typer(init_app, name="init")

wiki_app = typer.Typer(help="Quản lý wikis trong centralized MCP registry")
app.add_typer(wiki_app, name="wiki")

base_app = typer.Typer(help="Manage global llm-wiki-base runtime (~/.llm-wiki-base/)")
app.add_typer(base_app, name="base")

translate_app = typer.Typer(help="Translate wiki pages sang ngôn ngữ khác")
app.add_typer(translate_app, name="translate")

config_app = typer.Typer(help="Behavior config per-wiki (.llm-wiki.toml)")
app.add_typer(config_app, name="config")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"llm-wiki {__version__}")
        raise typer.Exit()


# ─────────────────────────────────────────────────────────────────────────────
# Init (interactive wizard + subcommands)
# ─────────────────────────────────────────────────────────────────────────────


@init_app.callback(invoke_without_command=True)
def init_interactive(ctx: typer.Context) -> None:
    """Interactive wizard: `llm-wiki init` walks through options.

    Nếu truyền subcommand (personal/project), bỏ qua wizard.
    """
    if ctx.invoked_subcommand is not None:
        return

    console.print("[bold cyan]llm-wiki init wizard[/bold cyan]")
    console.print("Tạo wiki mới (personal knowledge hoặc project wiki).\n")

    # 1. Wiki type
    wtype = Prompt.ask(
        "Loại wiki",
        choices=["personal", "project"],
        default="personal",
    )

    if wtype == "personal":
        _init_interactive_personal()
    else:
        _init_interactive_project()


def _init_interactive_personal() -> None:
    from llm_wiki.init_personal import run as run_personal
    from llm_wiki.config import supported_clients

    cwd = Path.cwd()
    default_name = cwd.name

    name = Prompt.ask("Tên wiki", default=default_name)

    client_str = Prompt.ask(
        "AI client để cài MCP (cách nhau bằng dấu phẩy)",
        default="claude",
    )
    clients = [c.strip() for c in client_str.split(",") if c.strip()]

    for c in clients:
        if c not in supported_clients():
            console.print(f"[red]Error:[/red] unsupported client '{c}'. Supported: {supported_clients()}")
            raise typer.Exit(1)

    do_mcp = Confirm.ask("Cài centralized MCP config không?", default=True)
    do_skills = Confirm.ask("Copy skills vào .agents/skills/ không?", default=True)

    console.print()
    run_personal(
        cwd=cwd,
        name=name,
        force=False,
        skills_target="universal" if do_skills else "skip",
        clients=clients,
        skip_mcp=not do_mcp,
    )


def _init_interactive_project() -> None:
    from llm_wiki.init_project import run as run_project
    from llm_wiki.config import supported_clients

    root = Path.cwd()
    default_subdir = "project-wiki"

    root_str = Prompt.ask("Project root", default=str(root))
    root = Path(root_str).resolve()

    wiki_dir = Prompt.ask("Wiki subdir (under project root)", default=default_subdir)

    client_str = Prompt.ask(
        "AI client để cài MCP (cách nhau bằng dấu phẩy)",
        default="claude",
    )
    clients = [c.strip() for c in client_str.split(",") if c.strip()]

    for c in clients:
        if c not in supported_clients():
            console.print(f"[red]Error:[/red] unsupported client '{c}'. Supported: {supported_clients()}")
            raise typer.Exit(1)

    do_mcp = Confirm.ask("Cài centralized MCP config không?", default=True)
    do_skills = Confirm.ask("Copy skills vào .agents/skills/ không?", default=True)

    console.print()
    run_project(
        root=root,
        wiki_subdir=wiki_dir,
        clients=clients,
        force=False,
        skills_target="universal" if do_skills else "skip",
        skip_mcp=not do_mcp,
    )


@init_app.command("personal")
def init_personal(
    here: bool = typer.Option(True, "--here", help="Init tại cwd (in-place)."),
    name: str | None = typer.Option(None, "--name", "-n", help="Wiki name (default: tên folder)."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirm nếu dir có content."),
    client: list[str] = typer.Option(
        ["claude"], "--client", "-c",
        help="AI client để cài centralized MCP. Có thể truyền nhiều lần: -c claude -c opencode.",
    ),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Skip centralized MCP config install."),
    skills_target: str = typer.Option(
        "universal", "--skills-target",
        help="Skill install location: 'universal' (<wiki>/.agents/skills/), 'claude' (.claude/skills/ + symlink), 'both' (copy cả 2).",
    ),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip skill install."),
) -> None:
    """Init 1 personal knowledge wiki tại cwd. In-place. Cài MCP + registry mặc định."""
    from llm_wiki.init_personal import run
    cwd = Path.cwd()
    target = "skip" if no_skills else skills_target
    run(cwd=cwd, name=name, force=force, skills_target=target, clients=client, skip_mcp=no_mcp)


@init_app.command("project")
def init_project(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root (default: cwd)."),
    wiki_dir: str = typer.Option(
        "project-wiki", "--wiki-dir", "-w",
        help="Subfolder dưới project root để chứa wiki data.",
    ),
    client: list[str] = typer.Option(
        ["claude"], "--client", "-c",
        help="AI client để cài centralized MCP. Có thể truyền nhiều lần: -c claude -c opencode.",
    ),
    server_name: str = typer.Option(
        "llm-wiki-base-mcp", "--server-name", "-s",
        help="Tên centralized MCP server (shared across all wikis trên máy).",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirm nếu wiki subdir có content."),
    skills_target: str = typer.Option(
        "universal", "--skills-target",
        help="Skill install location: 'universal' (<wiki>/.agents/skills/), 'claude', 'both'.",
    ),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip skill install."),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Skip centralized MCP config install."),
) -> None:
    """Init project wiki: tạo <root>/<wiki-dir>/ + register vào TOML + centralized MCP + skills."""
    from llm_wiki.init_project import run
    target = "skip" if no_skills else skills_target
    run(
        root=root,
        wiki_subdir=wiki_dir,
        clients=client,
        server_name=server_name,
        force=force,
        skills_target=target,
        skip_mcp=no_mcp,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Wiki management (registry)
# ─────────────────────────────────────────────────────────────────────────────


@wiki_app.command("list")
def wiki_list_cmd() -> None:
    """Liệt kê tất cả wikis trong centralized MCP registry."""
    from llm_wiki.registry import list_wikis
    wikis = list_wikis()
    if not wikis:
        console.print("[dim]Registry rỗng. Chạy `llm-wiki init` để tạo wiki đầu tiên.[/dim]")
        return
    console.print(f"[bold]{len(wikis)} wiki(s) trong registry:[/bold]\n")
    for w in wikis:
        tag = "project" if w.get("type") == "project" else "personal"
        console.print(f"  [cyan]{w['name']}[/cyan] ([dim]{tag}[/dim])")
        console.print(f"    path: {w['path']}")
        if w.get("added"):
            console.print(f"    added: {w['added']}")
    console.print()
    console.print("AI tool dùng param `wiki=<name>` để target wiki cụ thể.")
    console.print("Để trống `wiki=` để search cross-wiki (bao gồm personal wiki).")


@wiki_app.command("add")
def wiki_add_cmd(
    name: str = typer.Argument(..., help="Wiki name (dùng làm identifier trong MCP)."),
    path: str = typer.Argument(..., help="Đường dẫn tuyệt đối tới wiki root."),
    type: str = typer.Option("personal", "--type", "-t", help="personal hoặc project."),
) -> None:
    """Đăng ký 1 wiki đã tồn tại vào centralized MCP registry."""
    from llm_wiki.registry import add_wiki, get_wiki
    wiki_path = Path(path).resolve()
    if not wiki_path.exists():
        console.print(f"[red]Error:[/red] path không tồn tại: {wiki_path}")
        raise typer.Exit(1)
    add_wiki(name, str(wiki_path), wiki_type=type)
    console.print(f"[green]✓[/green] registered: '{name}' (type={type}) → {wiki_path}")


@wiki_app.command("remove")
def wiki_remove_cmd(
    name: str = typer.Argument(..., help="Wiki name để xóa khỏi registry."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirm."),
) -> None:
    """Xóa 1 wiki khỏi registry (không xóa files)."""
    from llm_wiki.registry import remove_wiki, get_wiki
    if not get_wiki(name):
        console.print(f"[red]Error:[/red] wiki '{name}' không có trong registry.")
        raise typer.Exit(1)
    if not force:
        if not Confirm.ask(f"Xóa '{name}' khỏi registry? (files không bị xóa)"):
            raise typer.Exit(0)
    if remove_wiki(name):
        console.print(f"[green]✓[/green] removed '{name}' from registry.")


# ─────────────────────────────────────────────────────────────────────────────
# Global base (runtime) management
# ─────────────────────────────────────────────────────────────────────────────


@base_app.command("install")
def base_install(
    dir: Path = typer.Option(
        None, "--dir", "-d",
        help="Target dir (default: ~/.llm-wiki-base). Override qua env LLM_WIKI_BASE_DIR.",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Recreate venv + reinstall requirements."),
) -> None:
    """Install global llm-wiki-base runtime (tools/, rag/, scripts/, .venv/).

    Chạy 1 lần sau khi `pip install llm-wiki`. Idempotent — chạy lại để sync
    tools/rag/scripts mới nhất từ package, bao gồm centralized MCP server.
    """
    base = install_base(base_dir=dir, force=force)
    console.print(f"[green]✓[/green] llm-wiki-base installed at: {base}")
    console.print(f"  python: {get_base_python()}")
    console.print()
    console.print("Next: cd vào 1 folder trống rồi `llm-wiki init` để tạo wiki data + MCP.")


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
    full: bool = typer.Option(False, "--full", help="Rebuild toàn bộ từ đầu (bỏ qua content-hash). Bắt buộc sau khi đổi embed_model/chunk_tokens/vector."),
    check: bool = typer.Option(False, "--check", help="Dry-run: báo sẽ index/xoá gì + config drift, KHÔNG ghi."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Rebuild search DB + RAG index. Mặc định tăng dần theo content-hash."""
    args = []
    if full:
        args.append("--full")
    if check:
        args.append("--check")
    _run_base_tool("reindex.py", args, root)


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


# ─────────────────────────────────────────────────────────────────────────────
# Translation
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Config (.llm-wiki.toml)
# ─────────────────────────────────────────────────────────────────────────────


# Env override map cho các key đã migrate từ env vars.
_ENV_KEYS: dict[tuple[str, ...], str] = {
    ("retrieval", "bm25_weight"): "WIKI_BM25_WEIGHT",
    ("retrieval", "vec_weight"): "WIKI_VEC_WEIGHT",
    ("retrieval", "index", "embed_model"): "WIKI_EMBED_MODEL",
}


def _print_config(cfg: dict, raw: dict, prefix: str = "") -> None:
    for k, v in cfg.items():
        path = prefix + k
        if isinstance(v, dict):
            console.print(f"[bold]{path}[/bold]")
            _print_config(v, raw.get(k, {}) if isinstance(raw.get(k), dict) else {}, path + ".")
            continue
        if _ENV_KEYS.get(tuple(path.split("."))) and os.environ.get(_ENV_KEYS[tuple(path.split("."))]):
            src = f"[yellow]env {_ENV_KEYS[tuple(path.split('.'))]}[/yellow]"
        elif k in raw:
            src = "[cyan]toml[/cyan]"
        else:
            src = "[dim]default[/dim]"
        console.print(f"  {path} = {v!r}  {src}")


@config_app.command("show")
def config_show(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd).",
    ),
) -> None:
    """In effective config: builtin defaults + .llm-wiki.toml + env override.

    Mỗi dòng đánh dấu nguồn: [default] / [toml] / [env ...].
    """
    from llm_wiki.config_file import get_config, load
    cfg = get_config(root)
    raw = load(root)
    if not raw:
        console.print("[dim](.llm-wiki.toml không tồn tại — dùng toàn bộ defaults)[/dim]\n")
    _print_config(cfg, raw)
    console.print()
    console.print("Đổi giá trị: sửa [cyan].llm-wiki.toml[/cyan] ở wiki root (env var override khi set).")


# ─────────────────────────────────────────────────────────────────────────────
# Verify (human duyệt artifact — cả personal + project)
# ─────────────────────────────────────────────────────────────────────────────


@app.command("verify")
def verify_cmd(
    path: str = typer.Argument(..., help="Page path relative to wiki root (vd: wiki/tech/concept/x.md)."),
    by: str | None = typer.Option(None, "--by", "-b", help="Human id duyệt (vd: nihmtaho). Bắt buộc khi set (không cần cho --unverify). Lưu dạng human:<id>."),
    unverify: bool = typer.Option(False, "--unverify", help="Xoá field verified (hạ về unverified)."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd).",
    ),
) -> None:
    """Human duyệt artifact: set/clear `verified` trong frontmatter page.

    Duyệt = set verified → trust tier *human-reviewed*. Cùng cơ chế cho
    personal + project wiki. Không LLM — deterministic frontmatter edit.
    """
    if not unverify and not by:
        console.print("[red]Error:[/red] thiếu --by (human id duyệt). Dùng --unverify để xoá verified.")
        raise typer.Exit(1)
    from llm_wiki import verify as verify_mod
    try:
        if unverify:
            p = verify_mod.unverify(root, path)
            console.print(f"[green]✓[/green] unverified → {p}")
        else:
            p = verify_mod.set_verified(root, path, by)
            console.print(f"[green]✓[/green] verified (human-reviewed) → {p}")
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
