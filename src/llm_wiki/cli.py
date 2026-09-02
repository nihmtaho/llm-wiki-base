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
    reindex         — wrapper: rebuild search DB + RAG (--full | --check)
    lint            — wrapper: health check (--fix để sửa an toàn)
    eval            — wrapper: đo retrieval trên query vàng P@k/R@k/MRR (--compare)
    watch           — wrapper: daemon scan inbox + ingest + reindex
    proposals       — duyệt staging edits của AI: list / show (diff) / apply / discard
    translate       — enable/disable/status/check (việc DỊCH là của skill, không phải CLI)
    config show     — in effective config (defaults + .llm-wiki.toml + env override)
    verify          — human duyệt artifact: set/clear `verified` trong frontmatter page
    doctor          — kiểm tra môi trường + nói rõ lệnh nào cần AI tool

Mọi lệnh ở trên là TẤT ĐỊNH. llm-wiki không gọi LLM: phần sinh nội dung (ingest ra
page, review, consolidate, translate, rerank) là SKILL chạy bằng LLM của AI tool đang
mở. `llm-wiki doctor` liệt kê đúng ranh giới đó khi bạn không chắc.
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

proposals_app = typer.Typer(help="Duyệt đề xuất sửa wiki (wiki/.proposals/) của AI")
app.add_typer(proposals_app, name="proposals")

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
    lang = Prompt.ask(
        "Ngôn ngữ wiki (agent sẽ viết page bằng ngôn ngữ này)", default="en")

    client_str = Prompt.ask(
        "AI client để cài MCP (cách nhau bằng dấu phẩy)",
        default="claude",
    )
    clients = [c.strip() for c in client_str.split(",") if c.strip()]

    for c in clients:
        if c not in supported_clients():
            console.print(f"[red]Error:[/red] unsupported client '{c}'. Supported: {supported_clients()}")
            raise typer.Exit(1)

    do_mcp = Confirm.ask(
        "Cài centralized MCP config không? (user scope: mọi project trên máy thấy)",
        default=True)
    do_skills = Confirm.ask(
        "Cài skills vào .agents/skills/ không? (Command Code đọc trực tiếp; "
        "Claude/OpenCode được symlink thêm)",
        default=True)

    console.print()
    run_personal(
        cwd=cwd,
        name=name,
        force=False,
        skills_target="universal" if do_skills else "skip",
        clients=clients,
        skip_mcp=not do_mcp,
        lang=lang,
    )


def _init_interactive_project() -> None:
    from llm_wiki.init_project import run as run_project
    from llm_wiki.config import supported_clients

    root = Path.cwd()
    default_subdir = "project-wiki"

    root_str = Prompt.ask("Project root", default=str(root))
    root = Path(root_str).resolve()

    wiki_dir = Prompt.ask("Wiki subdir (under project root)", default=default_subdir)
    lang = Prompt.ask(
        "Ngôn ngữ wiki (agent sẽ viết page bằng ngôn ngữ này)", default="en")

    client_str = Prompt.ask(
        "AI client để cài MCP (cách nhau bằng dấu phẩy)",
        default="claude",
    )
    clients = [c.strip() for c in client_str.split(",") if c.strip()]

    for c in clients:
        if c not in supported_clients():
            console.print(f"[red]Error:[/red] unsupported client '{c}'. Supported: {supported_clients()}")
            raise typer.Exit(1)

    do_mcp = Confirm.ask(
        "Cài centralized MCP config không?", default=True)
    mcp_scope = "user"
    if do_mcp:
        mcp_scope = Prompt.ask(
            "  Scope của MCP entry",
            choices=["user", "project"],
            default="user",
        )
        console.print(f"  [dim]user    = file config cá nhân, mọi project thấy[/dim]")
        console.print(f"  [dim]project = <root>/.mcp.json, commit vào VCS cho cả team "
                      f"(chỉ claude/commandcode)[/dim]")
    do_skills = Confirm.ask(
        "Cài skills không? (wiki scope → <wiki-dir>/.agents/skills/, "
        "codebase scope → <root>/.agents/skills/)",
        default=True)

    console.print()
    run_project(
        root=root,
        wiki_subdir=wiki_dir,
        clients=clients,
        force=False,
        skills_target="universal" if do_skills else "skip",
        skip_mcp=not do_mcp,
        mcp_scope=mcp_scope,
        lang=lang,
    )


@init_app.command("personal")
def init_personal(
    here: bool = typer.Option(True, "--here", help="Init tại cwd (in-place)."),
    name: str | None = typer.Option(None, "--name", "-n", help="Wiki name (default: tên folder)."),
    lang: str | None = typer.Option(
        None, "--lang", "-l",
        help="Ngôn ngữ wiki ghi vào [wiki].lang (vd vi, en). Agent viết page bằng ngôn ngữ này.",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirm nếu dir có content."),
    client: list[str] = typer.Option(
        ["claude"], "--client", "-c",
        help="AI client để cài centralized MCP: claude | opencode | zed | commandcode. "
             "Truyền nhiều lần: -c claude -c commandcode.",
    ),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Skip centralized MCP config install."),
    mcp_scope: str = typer.Option(
        "user", "--mcp-scope",
        help="'user' = file config cá nhân (mọi project thấy); "
             "'project' = <root>/.mcp.json (commit vào VCS; chỉ claude/commandcode).",
    ),
    skills_target: str = typer.Option(
        "universal", "--skills-target",
        help="Nơi cài skill: 'universal' = <wiki>/.agents/skills/ (canonical, Claude/OpenCode "
             "được symlink vào); 'claude' = thêm symlink .claude/skills/; 'both' = + "
             ".opencode/commands/; 'skip'.",
    ),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip skill install."),
    no_register: bool = typer.Option(
        False, "--no-register",
        help="Không ghi wiki vào registry.toml (test/script — tránh làm bẩn registry thật).",
    ),
) -> None:
    """Init 1 personal knowledge wiki tại cwd. In-place. Cài MCP + registry mặc định."""
    from llm_wiki.init_personal import run
    cwd = Path.cwd()
    target = "skip" if no_skills else skills_target
    run(cwd=cwd, name=name, force=force, skills_target=target, clients=client,
        skip_mcp=no_mcp, mcp_scope=mcp_scope, lang=lang, register=not no_register)


@init_app.command("project")
def init_project(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Project root (default: cwd)."),
    wiki_dir: str = typer.Option(
        "project-wiki", "--wiki-dir", "-w",
        help="Subfolder dưới project root để chứa wiki data.",
    ),
    lang: str | None = typer.Option(
        None, "--lang", "-l",
        help="Ngôn ngữ wiki ghi vào [wiki].lang (vd vi, en).",
    ),
    client: list[str] = typer.Option(
        ["claude"], "--client", "-c",
        help="AI client để cài centralized MCP: claude | opencode | zed | commandcode.",
    ),
    server_name: str = typer.Option(
        "llm-wiki-base-mcp", "--server-name", "-s",
        help="Tên centralized MCP server (shared across all wikis trên máy).",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirm nếu wiki subdir có content."),
    skills_target: str = typer.Option(
        "universal", "--skills-target",
        help="Nơi cài skill: 'universal' (canonical .agents/skills/ + link client), "
             "'claude', 'both', 'skip'.",
    ),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip skill install."),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Skip centralized MCP config install."),
    mcp_scope: str = typer.Option(
        "user", "--mcp-scope",
        help="'user' (mặc định) = file config cá nhân; 'project' = <root>/.mcp.json "
             "commit vào VCS, cả team dùng (chỉ claude/commandcode).",
    ),
    no_register: bool = typer.Option(
        False, "--no-register",
        help="Không ghi wiki vào registry.toml (test/script — tránh làm bẩn registry thật).",
    ),
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
        mcp_scope=mcp_scope,
        lang=lang,
        register=not no_register,
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
        console.print(f"    id:   {w.get('id') or '[dim]chưa có — chạy `llm-wiki wiki add` lại[/dim]'}")
        console.print(f"    path: {w['path']}")
        if w.get("added"):
            console.print(f"    added: {w['added']}")
    console.print()
    console.print("AI tool dùng param `wiki=<name>` để target wiki cụ thể "
                  "(accept cả `id`).")
    console.print("Để trống `wiki=` để search cross-wiki (bao gồm personal wiki).")
    console.print("[dim]Trùng name + khác path → init tự thêm hậu tố -<uuid8>, "
                  "không đá nhau.[/dim]")


@wiki_app.command("add")
def wiki_add_cmd(
    name: str = typer.Argument(..., help="Wiki name (dùng làm identifier trong MCP)."),
    path: str = typer.Argument(..., help="Đường dẫn tuyệt đối tới wiki root."),
    type: str = typer.Option("personal", "--type", "-t", help="personal hoặc project."),
) -> None:
    """Đăng ký 1 wiki đã tồn tại vào centralized MCP registry."""
    from llm_wiki.registry import add_wiki
    wiki_path = Path(path).resolve()
    if not wiki_path.exists():
        console.print(f"[red]Error:[/red] path không tồn tại: {wiki_path}")
        raise typer.Exit(1)
    used = add_wiki(name, str(wiki_path), wiki_type=type)
    if used != name:
        console.print(f"[yellow]![/yellow] name '{name}' đã bị wiki khác chiếm "
                      f"(khác path) → đăng ký là '{used}'")
    console.print(f"[green]✓[/green] registered: '{used}' (type={type}) → {wiki_path}")


@wiki_app.command("remove")
def wiki_remove_cmd(
    name: str = typer.Argument(..., help="Wiki name HOẶC id để xóa khỏi registry."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirm."),
) -> None:
    """Xóa 1 wiki khỏi registry (không xóa files)."""
    from llm_wiki.registry import remove_wiki, find
    if not find(name):
        console.print(f"[red]Error:[/red] wiki '{name}' không có trong registry "
                      f"(tra theo name hoặc id). Chạy `llm-wiki wiki list`.")
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


def _run_base_tool(tool_name: str, args: list[str], wiki_root: Path,
                   capture: bool = False) -> tuple[int, str]:
    """Chạy 1 script trong global base với context của wiki.

    Trả (exit_code, stdout). `capture=False` → in thẳng ra console (hành vi cũ).

    Không để traceback của subprocess leaks lên user: `check_call` ném
    CalledProcessError thô khi tool lỗi (kèm stack Python của CLI, không nói gì về
    wiki). Ở đây ta truyền exit code của tool + chỉ dẫn bước tiếp theo.
    """
    base = get_base_dir()
    py = get_base_python()
    script = base / "tools" / tool_name
    if not script.exists():
        console.print(f"[red]Error:[/red] {script} không tồn tại.")
        console.print("  Chạy [cyan]llm-wiki base install[/cyan] để dựng lại runtime.")
        raise typer.Exit(1)
    if not Path(py).exists():
        console.print(f"[red]Error:[/red] thiếu python của base venv: {py}")
        console.print("  Chạy [cyan]llm-wiki base install --force[/cyan] để tạo lại venv.")
        raise typer.Exit(1)

    env = os.environ.copy()
    env["WIKI_ROOT"] = str(Path(wiki_root).resolve())
    cmd = [str(py), str(script), *args]
    try:
        if capture:
            r = subprocess.run(cmd, cwd=str(wiki_root), env=env, capture_output=True,
                               text=True)
            if r.stdout:
                console.print(r.stdout, end="")
            if r.returncode != 0 and r.stderr:
                console.print(f"[red]{r.stderr.strip()}[/red]")
            return r.returncode, r.stdout or ""
        subprocess.run(cmd, cwd=str(wiki_root), env=env, check=True)
        return 0, ""
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] `llm-wiki {tool_name.replace('.py', '')}` "
                      f"thất bại (exit {e.returncode}).")
        console.print("  Xem lại message phía trên; nếu là lỗi DB/index, chạy "
                      "[cyan]llm-wiki reindex --check[/cyan] rồi "
                      "[cyan]llm-wiki doctor[/cyan].")
        raise typer.Exit(e.returncode or 1)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] không chạy được {py} — base venv hỏng?")
        console.print("  Chạy [cyan]llm-wiki base install --force[/cyan].")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        raise typer.Exit(130)


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
    fix: bool = typer.Option(False, "--fix", help="Sửa an toàn: xoá dangling rows + thêm index entry còn thiếu."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Health-check wiki: orphan, broken link, missing file, stale claim."""
    args = ["--root", str(root)]
    if fix:
        args.append("--fix")
    _run_base_tool("lint.py", args, root)


@app.command("eval")
def eval_cmd(
    k: int = typer.Option(0, "--k", help="Cutoff metric (mặc định: [eval].k, rồi top_n_final)."),
    compare: bool = typer.Option(False, "--compare", help="So sánh profile tier1-weighted / rrf-text / rrf+vector."),
    as_json: bool = typer.Option(False, "--json", help="In JSON thay vì bảng."),
    init: bool = typer.Option(False, "--init", help="Tạo eval/golden.toml từ template."),
    no_save: bool = typer.Option(False, "--no-save", help="Không append vào eval/results.json."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="In số liệu từng query."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Đo chất lượng retrieval trên bộ query vàng (P@k / R@k / MRR).

    Read-only với wiki: không sửa markdown, không ghi wiki/log.md.
    """
    args = []
    if k:
        args += ["--k", str(k)]
    if compare:
        args.append("--compare")
    if as_json:
        args.append("--json")
    if init:
        args.append("--init")
    if no_save:
        args.append("--no-save")
    if verbose:
        args.append("-v")
    _run_base_tool("eval.py", args, root)


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
# Lưu ý: installer KHÔNG pin các env này trong MCP server entry nữa — pin ở đó
# làm `.llm-wiki.toml` bị vô hiệu riêng trong MCP (env > TOML). Xem installer.py.
_ENV_KEYS: dict[tuple[str, ...], str] = {
    ("retrieval", "bm25_weight"): "WIKI_BM25_WEIGHT",
    ("retrieval", "vec_weight"): "WIKI_VEC_WEIGHT",
    ("retrieval", "fusion"): "WIKI_FUSION",
    ("retrieval", "chunk_bm25"): "WIKI_CHUNK_BM25",
    ("retrieval", "index", "embed_model"): "WIKI_EMBED_MODEL",
}

# Env luôn là string; cast theo kiểu của builtin default để in ĐÚNG giá trị
# hiệu lực (không chỉ dán nhãn [env ...] rồi in giá trị TOML/default).
_ENV_CAST = {
    "WIKI_BM25_WEIGHT": float,
    "WIKI_VEC_WEIGHT": float,
    "WIKI_CHUNK_BM25": lambda s: s.strip().lower() not in ("0", "false", "no", "off"),
}


def _env_effective(env_name: str, current):
    """Giá trị thực sự được dùng khi env này đang set (mô phỏng config_file.effective)."""
    raw = os.environ.get(env_name)
    if raw is None or raw == "":
        return current, False
    cast = _ENV_CAST.get(env_name)
    if cast is None:
        return raw, True
    try:
        return cast(raw), True
    except (ValueError, AttributeError):
        return f"{raw} (không parse được)", True


def _print_config(cfg: dict, raw: dict, prefix: str = "") -> None:
    for k, v in cfg.items():
        path = prefix + k
        if isinstance(v, dict):
            console.print(f"[bold]{path}[/bold]")
            _print_config(v, raw.get(k, {}) if isinstance(raw.get(k), dict) else {}, path + ".")
            continue
        env_name = _ENV_KEYS.get(tuple(path.split(".")))
        shown, from_env = (v, False)
        if env_name:
            shown, from_env = _env_effective(env_name, v)
        if from_env:
            src = f"[yellow]env {env_name}[/yellow]"
        elif k in raw:
            src = "[cyan]toml[/cyan]"
        else:
            src = "[dim]default[/dim]"
        console.print(f"  {path} = {shown!r}  {src}")


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


# ─────────────────────────────────────────────────────────────────────────────
# Proposals — duyệt staging edits của AI (wiki/.proposals/)
# ─────────────────────────────────────────────────────────────────────────────


@proposals_app.command("list")
def proposals_list(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """Liệt kê đề xuất đang chờ duyệt + độ lớn diff so với page hiện tại."""
    _run_base_tool("proposals.py", ["list"], root)


@proposals_app.command("show")
def proposals_show(
    name: str = typer.Argument(..., help="Tên proposal (hoặc một phần, nếu duy nhất)."),
    context: int = typer.Option(3, "--context", "-C", help="Số dòng ngữ cảnh quanh diff."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """In metadata + unified diff của proposal so với page đích hiện tại."""
    _run_base_tool("proposals.py", ["show", name, "--context", str(context)], root)


@proposals_app.command("apply")
def proposals_apply(
    name: str = typer.Argument(..., help="Tên proposal."),
    target: str | None = typer.Option(
        None, "--target", help="Ép path đích (chỉ cần cho proposal cũ không có metadata)."),
    by: str | None = typer.Option(
        None, "--by", "-b", help="Human id — nếu đưa, page được set `verified` sau khi apply."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """Chấp nhận 1 proposal: ghi vào page đích + log + reindex + xoá proposal.

    `--by <id>` là chữ ký của BẠN (trust tier human-reviewed) — không truyền thì
    page vẫn unverified và bạn duyệt sau bằng `llm-wiki verify`.
    """
    import re as _re
    args = ["apply", name]
    if target:
        args += ["--target", target]
    rc, out = _run_base_tool("proposals.py", args, root, capture=True)
    if rc != 0:
        raise typer.Exit(rc)
    if not by:
        return
    # proposals.py in `APPLIED\t<rel>` trước khi xoá file — không còn cách nào khác
    # để biết target sau khi proposal đã không còn trên đĩa.
    m = _re.search(r"^APPLIED\t(.+)$", out, _re.MULTILINE)
    applied = target or (m.group(1) if m else None)
    if not applied:
        console.print("[yellow]![/yellow] không đọc được path đích từ output — tự duyệt: "
                      f"`llm-wiki verify <path> --by {by}`")
        return
    from llm_wiki import verify as verify_mod
    try:
        p = verify_mod.set_verified(root, applied, by)
        console.print(f"[green]✓[/green] verified (human-reviewed) → {p}")
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[yellow]![/yellow] apply OK nhưng không set verified được: {e}")
        console.print(f"  Tự chạy: llm-wiki verify <path> --by {by}")


@proposals_app.command("new")
def proposals_new(
    target: str = typer.Option(..., "--target", "-t",
                               help="Page đích tương đối trong wiki (vd wiki/<domain>/concept/x.md)."),
    file: str = typer.Option("-", "--file", "-f",
                             help="File chứa nội dung đề xuất; '-' = đọc từ stdin."),
    by: str = typer.Option("", "--by", help="Ai đề xuất (tool/client) — ghi vào metadata."),
    note: str = typer.Option("", "--note", help="Lý do đề xuất, hiển thị trong `show`."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """Tạo 1 proposal STAGING (không sửa page). Cùng format MCP `wiki_propose_edit`."""
    args = ["new", "--target", target, "--file", file, "--by", by, "--note", note]
    _run_base_tool("proposals.py", args, root)


@proposals_app.command("discard")
def proposals_discard(
    name: str = typer.Argument(..., help="Tên proposal."),
    force: bool = typer.Option(False, "--force", "-f", help="Xác nhận xoá."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """Từ bỏ 1 proposal (xoá file, không ghi gì vào wiki)."""
    args = ["discard", name]
    if force:
        args.append("--force")
    _run_base_tool("proposals.py", args, root)


# ─────────────────────────────────────────────────────────────────────────────
# Doctor
# ─────────────────────────────────────────────────────────────────────────────


_SKILL_LAYER = [
    ("ingest ra wiki page", "llm-wiki-ingest",
     "`llm-wiki ingest` chỉ INDEX 1 file vào DB; người VIẾT page là skill."),
    ("trả lời câu hỏi + rerank", "llm-wiki-query",
     "retrieval là MCP/CLI, nhưng chấm ứng viên và tổng hợp trả lời là LLM của AI tool."),
    ("review ngữ nghĩa (mâu thuẫn, stale)", "llm-wiki-review",
     "`llm-wiki lint` chỉ kiểm cấu trúc tất định."),
    ("consolidate / gộp concept", "llm-wiki-consolidate", "additive merge + distill-verify."),
    ("dịch page", "llm-wiki-translate",
     "`llm-wiki translate enable` chỉ ghi config; bản dịch do skill tạo."),
    ("research xuyên wiki", "llm-wiki-research", "cài ở root codebase, không nằm trong wiki."),
]


@app.command("doctor")
def doctor_cmd(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root cần kiểm (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """Kiểm tra môi trường: base runtime, tools lệch, deps, registry, wiki hiện tại.

    Báo rõ phần nào FAIL (chặn dùng), phần nào WARN (chạy được nhưng mất tính năng),
    và ranh giới CLI-vs-skill (việc gì bắt buộc phải có AI tool).
    """
    from llm_wiki._package_data import package_path
    base = get_base_dir()
    fails: list[str] = []
    warns: list[str] = []

    def ok(msg: str) -> None:
        console.print(f"  [green]✓[/green] {msg}")

    def warn(msg: str) -> None:
        warns.append(msg)
        console.print(f"  [yellow]![/yellow] {msg}")

    def fail(msg: str) -> None:
        fails.append(msg)
        console.print(f"  [red]✗[/red] {msg}")

    console.print("[bold]Môi trường[/bold]")
    if base.exists():
        ok(f"base runtime: {base}")
    else:
        fail(f"base runtime chưa cài: {base} → chạy `llm-wiki base install`")
    py = get_base_python()
    ok(f"base python: {py}") if py.exists() else fail(f"thiếu venv python: {py} → `llm-wiki base install --force`")

    src_tools = package_path("base_tools")
    if src_tools.is_dir() and (base / "tools").is_dir():
        stale = sorted(f.name for f in src_tools.glob("*.py")
                       if not (base / "tools" / f.name).exists()
                       or (base / "tools" / f.name).read_bytes() != f.read_bytes())
        if stale:
            warn(f"tools/ trong base LỆCH với package ({len(stale)} file) → chạy "
                 f"`llm-wiki base install`: {', '.join(stale[:6])}")
        else:
            ok("tools/ đồng bộ với package")

    console.print("\n[bold]Dependencies (base venv)[/bold]")
    # tomli CHỈ cần khi base venv là Python <3.11 (từ 3.11 có tomllib trong stdlib).
    py311 = True
    if py.exists():
        py311 = subprocess.run(
            [str(py), "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
            capture_output=True).returncode == 0
    checks = [("mcp", "MCP servers cần package này"),
              ("fastembed", "kênh vector cần nó (bỏ được nếu vector=false)")]
    if py311:
        ok("tomllib (stdlib Python ≥3.11)")
    else:
        checks.append(("tomli", "Python <3.11 cần để đọc .llm-wiki.toml"))
    for mod, why in checks:
        if not py.exists():
            break
        r = subprocess.run([str(py), "-c", f"import {mod}"], capture_output=True, text=True)
        if r.returncode == 0:
            ok(f"{mod}")
        elif mod == "fastembed":
            warn("fastembed thiếu → kênh vector chết, `eval --compare` sẽ báo [ERROR]")
        else:
            fail(f"{mod} thiếu → `pip install -r {base}/requirements.txt` trong base venv ({why})")

    console.print("\n[bold]Registry[/bold]")
    from llm_wiki.registry import list_wikis
    wikis = list_wikis()
    ok(f"{len(wikis)} wiki đã đăng ký") if wikis else warn(
        "registry rỗng → MCP không thấy wiki nào; chạy `llm-wiki init`")
    for w in wikis:
        if not Path(w.get("path", "")).exists():
            fail(f"'{w.get('name')}' trỏ tới path không còn tồn tại: {w.get('path')} "
                 f"→ `llm-wiki wiki remove {w.get('name')}`")
        if not w.get("id"):
            warn(f"'{w.get('name')}' chưa có id (UUID) — thêm lại bằng `llm-wiki wiki add`")

    console.print("\n[bold]Wiki hiện tại[/bold]")
    cfg = root / ".llm-wiki.toml"
    if cfg.is_file():
        ok(f".llm-wiki.toml: {cfg}")
        from llm_wiki.config_file import load as load_cfg
        prof = (load_cfg(root).get("wiki") or {}).get("profile")
        ok(f"\\[wiki].profile = {prof}") if prof else warn(
            "thiếu \\[wiki].profile → skill không biết đang ở chế độ nào; chạy lại "
            "`llm-wiki init personal|project` (nó idempotent)")
    else:
        warn(f"không có .llm-wiki.toml ở {root} (dùng defaults; đây có phải wiki root?)")
    if wikis and not any(Path(w.get("path", "")).resolve() == Path(root).resolve()
                         for w in wikis):
        warn(f"{root} CHƯA đăng ký trong registry → MCP không tìm thấy nó qua `wiki=`")
    props = list((root / "wiki" / ".proposals").glob("*")) if (root / "wiki" / ".proposals").is_dir() else []
    props = [p for p in props if p.is_file() and not p.name.startswith(".")]
    if props:
        warn(f"{len(props)} proposal đang chờ duyệt → `llm-wiki proposals list`")
    else:
        ok("không có proposal tồn đọng")

    console.print("\n[bold]Việc cần AI tool (CLI không tự làm)[/bold]")
    console.print("  llm-wiki KHÔNG gọi LLM. Các bước sinh nội dung chạy bằng LLM của")
    console.print("  AI tool đang mở, qua skill đã cài ở .agents/skills/:")
    for what, skill, why in _SKILL_LAYER:
        console.print(f"    · {what:<34} [cyan]{skill}[/cyan]")
        console.print(f"      [dim]{why}[/dim]")

    console.print()
    if fails:
        console.print(f"[red]doctor: {len(fails)} lỗi[/red], {len(warns)} cảnh báo")
        raise typer.Exit(1)
    console.print(f"[green]doctor: OK[/green]" + (f" — {len(warns)} cảnh báo" if warns else ""))


if __name__ == "__main__":
    app()
