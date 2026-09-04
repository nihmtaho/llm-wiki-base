"""llm-wiki CLI — Typer app.

Subcommands (canonical):
    setup personal   — init personal knowledge wiki in-place (data only + MCP + registry)
    setup project    — init project wiki + install centralized MCP per-project + register
    setup tools      — install global runtime to ~/.llm-wiki-base/ (1 lần per máy)
    setup doctor     — kiểm tra môi trường + nói rõ lệnh nào cần AI tool
    wiki ingest      — wrapper: gọi global tools/ingest.py với cwd context
    wiki reindex     — wrapper: rebuild search DB + RAG (--full | --check)
    check lint       — wrapper: health check (--fix để sửa an toàn)
    check verify     — human duyệt artifact: set/clear `verified` trong frontmatter page
    check eval       — wrapper: đo retrieval trên query vàng P@k/R@k/MRR (--compare)
    review ...       — duyệt staging edits của AI: list / show (diff) / apply / discard
    watch            — wrapper: daemon scan inbox + ingest + reindex
    serve --mcp      — chạy centralized MCP server (stdio) cho AI tool
    translate        — enable/disable/status/check (việc DỊCH là của skill, không phải CLI)
    config show      — in effective config (defaults + .llm-wiki.toml + env override)

Mọi lệnh ở trên là TẤT ĐỊNH. llm-wiki không gọi LLM: phần sinh nội dung (ingest ra
page, review, consolidate, translate, rerank) là SKILL chạy bằng LLM của AI tool đang
mở. `llm-wiki setup doctor` liệt kê đúng ranh giới đó khi bạn không chắc.
"""
import os
import subprocess
import sys
from pathlib import Path

import typer
from rich.prompt import Confirm, Prompt

from llm_wiki import _ui
from llm_wiki._ui import console

from llm_wiki import __version__
from llm_wiki.base import get_base_dir, get_base_python, install_base

app = typer.Typer(
    name="llm-wiki",
    help="LLM-maintained wiki với hybrid BM25+vector search, centralized MCP bridge, multi-base init.",
    no_args_is_help=True,
    add_completion=False,
)

# Hidden pre-redesign group (spec §7): no callback — bare `llm-wiki init`
# shows init help, `init personal|project` still work as hidden aliases.
# The wizard lives at `setup` (setup_interactive) since Task 7.
init_app = typer.Typer(
    help="Init mới 1 wiki (personal hoặc project)",
    hidden=True,
    epilog="Examples:\n  llm-wiki init\n  llm-wiki setup personal --name notes --no-mcp",
)

setup_app = typer.Typer(
    help="Set up wikis, tools and health checks",
    epilog="Examples:\n  llm-wiki setup\n  llm-wiki setup personal --name notes --yes",
)
wiki_app = typer.Typer(help="Quản lý wikis trong centralized MCP registry")
check_app = typer.Typer(help="Check wiki health: lint, verify, eval")
review_app = typer.Typer(help="Review AI-proposed wiki edits (wiki/.proposals/)")
translate_app = typer.Typer(help="Translate wiki pages sang ngôn ngữ khác")
config_app = typer.Typer(help="Behavior config per-wiki (.llm-wiki.toml)")

# Root --help renders in registration order (spec §6 goal order): singles
# from @app.command first, then groups in add_typer order. watch/serve must
# come LAST, so they live in an unnamed sub-app merged at the end instead of
# @app.command (Typer emits registered_commands before registered_groups).
_tail_app = typer.Typer()

# Hidden alias app for pre-redesign `base *` paths (spec §7). The canonical
# handlers now live under `setup tools` / `config path`; this app only
# re-registers the same functions under their old names.
_alias_base_app = typer.Typer(hidden=True)

# Hidden alias app for pre-redesign `proposals *` paths (spec §7). The five
# commands below re-register the `review_*` handlers under their old names.
_alias_proposals_app = typer.Typer(hidden=True)

app.add_typer(init_app, name="init")
app.add_typer(setup_app, name="setup")
app.add_typer(wiki_app, name="wiki")
app.add_typer(check_app, name="check")
app.add_typer(review_app, name="review")
app.add_typer(translate_app, name="translate")
app.add_typer(config_app, name="config")
app.add_typer(_alias_base_app, name="base")
app.add_typer(_alias_proposals_app, name="proposals")
app.add_typer(_tail_app)


@app.callback()
def _global_options(
    ctx: typer.Context,
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Facts only, no panels."),
    no_color: bool = typer.Option(False, "--no-color", help="Strip ANSI colors."),
    debug: bool = typer.Option(False, "--debug", help="Show full tracebacks on errors."),
) -> None:
    _ui.set_quiet(quiet)
    _ui.set_no_color(no_color)
    _ui.set_debug(debug)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"llm-wiki {__version__}")
        raise typer.Exit()


# ─────────────────────────────────────────────────────────────────────────────
# Setup wizard (slim: location → profile → clients, then summary + confirm)
# ─────────────────────────────────────────────────────────────────────────────


@setup_app.callback(invoke_without_command=True)
def setup_interactive(ctx: typer.Context) -> None:
    """Slim wizard: location → profile → clients, then summary + confirm.
    \f
    Examples:
        llm-wiki setup
        llm-wiki setup personal --name notes --yes
    """
    if ctx.invoked_subcommand is not None:
        return
    _ui.banner("llm-wiki setup", "Tạo wiki mới trong 3 câu hỏi.")
    wtype = Prompt.ask("Loại wiki", choices=["personal", "project"], default="personal")
    if wtype == "personal":
        _slim_personal()
    else:
        _slim_project()


def _parse_clients(client_str: str) -> list[str]:
    return [c.strip() for c in client_str.split(",") if c.strip()]


def _validate_clients(clients: list[str]) -> None:
    from llm_wiki.config import supported_clients
    supported = supported_clients()
    for c in clients:
        if c not in supported:
            _ui.err_panel(f"unsupported client '{c}'. Supported: {supported}",
                          "use --client claude (repeat -c per client)")
            raise typer.Exit(1)


def _prompt_interactive_extras(lang: str, skills_target: str,
                               skip_mcp: bool) -> tuple[str, str, bool]:
    """Dropped questions, restored by `--interactive` (spec §5)."""
    lang = Prompt.ask(
        "Ngôn ngữ wiki (agent sẽ viết page bằng ngôn ngữ này)", default=lang)
    skills_target = Prompt.ask(
        "Skills target", choices=["universal", "claude", "both", "skip"],
        default=skills_target)
    do_mcp = Confirm.ask("Cài MCP vào wiki không?", default=not skip_mcp)
    return lang, skills_target, not do_mcp


def _confirm_and_run_personal(cwd: Path, name: str | None, lang: str,
                              clients: list[str], skills_target: str,
                              skip_mcp: bool, yes: bool, register: bool = True,
                              force: bool = False) -> None:
    from llm_wiki.init_personal import run as run_personal
    facts = [
        "Loại:     personal",
        f"Tên:      {name or cwd.name}",
        f"Path:     {cwd}",
        f"Lang:     {lang}",
        f"Clients:  {', '.join(clients) if clients else '(none)'}",
        f"Skills:   {skills_target}",
        f"MCP:      {'skip' if skip_mcp else 'install'}",
    ]
    _ui.ok_panel("Ready to create", facts)
    if not (yes or force) and not Confirm.ask("Tạo wiki?", default=True):
        raise typer.Exit(0)
    # Summary confirm subsumes run()'s empty-dir confirm → force=True avoids a 2nd prompt.
    run_personal(cwd=cwd, name=name, force=True, skills_target=skills_target,
                 clients=clients, skip_mcp=skip_mcp, lang=lang, register=register)


def _confirm_and_run_project(root: Path, wiki_subdir: str, lang: str,
                             clients: list[str], skills_target: str,
                             skip_mcp: bool, yes: bool, register: bool = True,
                             force: bool = False,
                             server_name: str | None = None) -> None:
    from llm_wiki.init_project import run as run_project
    from llm_wiki.installer import CENTRALIZED_SERVER_NAME
    server_name = server_name or CENTRALIZED_SERVER_NAME
    facts = [
        "Loại:     project",
        f"Root:     {root}",
        f"Subdir:   {wiki_subdir}",
        f"Lang:     {lang}",
        f"Clients:  {', '.join(clients) if clients else '(none)'}",
        f"Skills:   {skills_target}",
        f"MCP:      {'skip' if skip_mcp else 'install'}",
        f"Server:   {server_name}",
    ]
    _ui.ok_panel("Ready to create", facts)
    if not (yes or force) and not Confirm.ask("Tạo wiki?", default=True):
        raise typer.Exit(0)
    run_project(root=root, wiki_subdir=wiki_subdir, clients=clients,
                server_name=server_name, force=True, skills_target=skills_target,
                skip_mcp=skip_mcp, lang=lang, register=register)


def _slim_personal() -> None:
    """Q1 location (name) → Q3 clients; lang/skills/MCP use fixed defaults
    (extras only via `setup personal|project --interactive`)."""
    cwd = Path.cwd()
    name = Prompt.ask("Tên wiki", default=cwd.name)
    clients = _parse_clients(Prompt.ask(
        "AI client để cài MCP (cách nhau bằng dấu phẩy)", default="claude"))
    _validate_clients(clients)
    lang, skills_target, skip_mcp = "en", "universal", False
    _confirm_and_run_personal(cwd, name, lang, clients, skills_target, skip_mcp, yes=False)


def _slim_project() -> None:
    """Q1 location (root + subdir) → Q3 clients; lang/skills/MCP use fixed defaults
    (extras only via `setup personal|project --interactive`)."""
    root = Path(Prompt.ask("Project root", default=str(Path.cwd()))).resolve()
    wiki_subdir = Prompt.ask("Wiki subdir (under project root)", default="project-wiki")
    clients = _parse_clients(Prompt.ask(
        "AI client để cài MCP (cách nhau bằng dấu phẩy)", default="claude"))
    _validate_clients(clients)
    lang, skills_target, skip_mcp = "en", "universal", False
    _confirm_and_run_project(root, wiki_subdir, lang, clients, skills_target, skip_mcp, yes=False)


@setup_app.command("personal")
@init_app.command("personal", hidden=True)
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
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Skip cài MCP vào per-project/personal wiki."),
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
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Bỏ qua màn hình confirm (scripts/CI). Không bao giờ hỏi.",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i",
        help="Hỏi thêm lang, skills target, skip MCP trước màn hình confirm.",
    ),
) -> None:
    """Init 1 personal knowledge wiki tại cwd. In-place. Cài MCP + registry mặc định.

    Examples:
        llm-wiki setup personal --name notes
        llm-wiki setup personal --name notes --client claude --client opencode
        llm-wiki setup personal --name notes --lang vi --no-mcp
    """
    cwd = Path.cwd()
    lang_val = lang or "en"
    target = "skip" if no_skills else skills_target
    skip_mcp_val = no_mcp
    clients = list(client)
    if interactive:
        client_str = Prompt.ask(
            "AI client để cài MCP (cách nhau bằng dấu phẩy)",
            default=",".join(clients) if clients else "claude",
        )
        clients = _parse_clients(client_str)
        lang_val, target, skip_mcp_val = _prompt_interactive_extras(
            lang_val, target, skip_mcp_val)
    _validate_clients(clients)
    _confirm_and_run_personal(cwd, name, lang_val, clients, target,
                              skip_mcp_val, yes=yes, register=not no_register,
                              force=force)


@setup_app.command("project")
@init_app.command("project", hidden=True)
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
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Skip cài MCP vào per-project wiki."),
    no_register: bool = typer.Option(
        False, "--no-register",
        help="Không ghi wiki vào registry.toml (test/script — tránh làm bẩn registry thật).",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Bỏ qua màn hình confirm (scripts/CI). Không bao giờ hỏi.",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i",
        help="Hỏi thêm lang, skills target, skip MCP trước màn hình confirm.",
    ),
) -> None:
    """Init project wiki: tạo <root>/<wiki-dir>/ + register vào TOML + MCP per-project + skills.

    Examples:
        llm-wiki setup project --root . --wiki-dir project-wiki
        llm-wiki setup project --root /path/to/repo --client claude --no-skills
    """
    lang_val = lang or "en"
    target = "skip" if no_skills else skills_target
    skip_mcp_val = no_mcp
    clients = list(client)
    if interactive:
        client_str = Prompt.ask(
            "AI client để cài MCP (cách nhau bằng dấu phẩy)",
            default=",".join(clients) if clients else "claude",
        )
        clients = _parse_clients(client_str)
        lang_val, target, skip_mcp_val = _prompt_interactive_extras(
            lang_val, target, skip_mcp_val)
    _validate_clients(clients)
    _confirm_and_run_project(root, wiki_dir, lang_val, clients, target,
                             skip_mcp_val, yes=yes, register=not no_register,
                             force=force, server_name=server_name)


# ─────────────────────────────────────────────────────────────────────────────
# Wiki management (registry)
# ─────────────────────────────────────────────────────────────────────────────


@wiki_app.command("list")
def wiki_list_cmd() -> None:
    """Liệt kê tất cả wikis trong centralized MCP registry.

    Examples:
        llm-wiki wiki list
    """
    from llm_wiki.registry import list_wikis
    wikis = list_wikis()
    if not wikis:
        if _ui.is_quiet():
            return
        console.print("[dim]Registry rỗng. Chạy `llm-wiki setup` để tạo wiki đầu tiên.[/dim]")
        return
    _ui.wiki_table(wikis)
    if any(not w.get("id") for w in wikis):
        console.print("[dim]ID trống → chạy `llm-wiki wiki add` lại.[/dim]")
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
    """Đăng ký 1 wiki đã tồn tại vào centralized MCP registry.

    Examples:
        llm-wiki wiki add notes /path/to/notes
        llm-wiki wiki add docs /path/to/repo/project-wiki --type project
    """
    from llm_wiki.registry import add_wiki
    wiki_path = Path(path).resolve()
    if not wiki_path.exists():
        _ui.err_panel(f"path không tồn tại: {wiki_path}", "llm-wiki wiki list")
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
    """Xóa 1 wiki khỏi registry (không xóa files).

    Examples:
        llm-wiki wiki remove notes
        llm-wiki wiki remove notes --force
    """
    from llm_wiki.registry import remove_wiki, find
    if not find(name):
        _ui.err_panel(f"wiki '{name}' không có trong registry", "llm-wiki wiki list")
        raise typer.Exit(1)
    if not force:
        if not Confirm.ask(f"Xóa '{name}' khỏi registry? (files không bị xóa)"):
            raise typer.Exit(0)
    if remove_wiki(name):
        console.print(f"[green]✓[/green] removed '{name}' from registry.")


# ─────────────────────────────────────────────────────────────────────────────
# Global base (runtime) management
# ─────────────────────────────────────────────────────────────────────────────


@setup_app.command("tools")
@_alias_base_app.command("install", hidden=True)
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

    Examples:
        llm-wiki setup tools
        llm-wiki setup tools --force
        llm-wiki setup tools --dir ~/.llm-wiki-base
    """
    base = install_base(base_dir=dir, force=force)
    _ui.done_panel("llm-wiki-base installed",
                   [f"at:     {base}", f"python: {get_base_python()}"])
    console.print()
    console.print("Next: cd vào 1 folder trống rồi `llm-wiki setup personal` để tạo wiki data + MCP.")


@config_app.command("path")
@_alias_base_app.command("path", hidden=True)
def base_path() -> None:
    """In đường dẫn global base hiện tại (env override hoặc default).

    Examples:
        llm-wiki config path
    """
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
        _ui.err_panel(f"{script} không tồn tại.", "llm-wiki setup tools")
        raise typer.Exit(1)
    if not Path(py).exists():
        _ui.err_panel(f"thiếu python của base venv: {py}", "llm-wiki setup tools --force")
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
        _ui.err_panel(f"`llm-wiki {tool_name.replace('.py', '')}` "
                      f"thất bại (exit {e.returncode}).",
                      "llm-wiki wiki reindex --check, then llm-wiki setup doctor")
        raise typer.Exit(e.returncode or 1)
    except FileNotFoundError:
        _ui.err_panel(f"không chạy được {py} — base venv hỏng?",
                      "llm-wiki setup tools --force")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        raise typer.Exit(130)


@wiki_app.command("ingest")
@app.command("ingest", hidden=True)
def ingest_cmd(
    path: str = typer.Argument(..., help="Source path relative to wiki root (vd: raw/inbox/foo.md)."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Ingest 1 source vào search DB. Chạy từ trong wiki dir.

    Examples:
        llm-wiki wiki ingest raw/inbox/foo.md
        llm-wiki wiki ingest raw/inbox/foo.md --root /path/to/wiki
    """
    target = Path(path)
    abs_target = target if target.is_absolute() else (root / target)
    _run_base_tool("ingest.py", [str(abs_target)], root)


@wiki_app.command("reindex")
@app.command("reindex", hidden=True)
def reindex_cmd(
    full: bool = typer.Option(False, "--full", help="Rebuild toàn bộ từ đầu (bỏ qua content-hash). Bắt buộc sau khi đổi embed_model/chunk_tokens/vector."),
    check: bool = typer.Option(False, "--check", help="Dry-run: báo sẽ index/xoá gì + config drift, KHÔNG ghi."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Rebuild search DB + RAG index. Mặc định tăng dần theo content-hash.

    Examples:
        llm-wiki wiki reindex
        llm-wiki wiki reindex --check
        llm-wiki wiki reindex --full
    """
    args = []
    if full:
        args.append("--full")
    if check:
        args.append("--check")
    _run_base_tool("reindex.py", args, root)


@check_app.command("lint")
@app.command("lint", hidden=True)
def lint_cmd(
    fix: bool = typer.Option(False, "--fix", help="Sửa an toàn: xoá dangling rows + thêm index entry còn thiếu."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Health-check wiki: orphan, broken link, missing file, stale claim.

    Examples:
        llm-wiki check lint
        llm-wiki check lint --fix
    """
    args = ["--root", str(root)]
    if fix:
        args.append("--fix")
    _run_base_tool("lint.py", args, root)


@check_app.command("eval")
@app.command("eval", hidden=True)
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

    Examples:
        llm-wiki check eval
        llm-wiki check eval --compare
        llm-wiki check eval --k 5 --verbose
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


@_tail_app.command("watch")
def watch_cmd(
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Daemon: scan raw/inbox/ → ingest → reindex → lint. Chạy từ trong wiki dir.

    Examples:
        llm-wiki watch
        llm-wiki watch --root /path/to/wiki
    """
    _run_base_tool("watch.py", [], root)


@_tail_app.command("serve")
def serve_cmd(
    mcp: bool = typer.Option(False, "--mcp", help="Chạy centralized MCP server (stdio)."),
) -> None:
    """Chạy MCP server cho AI tool — tương đương `llm-wiki serve --mcp`.

    Exec base python + tools/mcp_base_server.py (giữ đúng venv có mcp/fastembed,
    stdio pass-through cho JSON-RPC). Entry MCP trong file per-project wiki
    trỏ vào lệnh này: ["llm-wiki", "serve", "--mcp"].

    Examples:
        llm-wiki serve --mcp
    """
    if not mcp:
        _ui.err_panel("`llm-wiki serve` cần flag --mcp (stdio MCP server cho AI tool).",
                      "llm-wiki serve --mcp")
        raise typer.Exit(2)
    from llm_wiki.installer import CENTRALIZED_SERVER_SCRIPT
    base = get_base_dir()
    script = base / "tools" / CENTRALIZED_SERVER_SCRIPT
    py = get_base_python()
    if not script.exists():
        _ui.err_panel(f"{script} không tồn tại.", "llm-wiki setup tools")
        raise typer.Exit(1)
    if not Path(py).exists():
        _ui.err_panel(f"thiếu python của base venv: {py}", "llm-wiki setup tools --force")
        raise typer.Exit(1)
    env = os.environ.copy()
    env.setdefault("LLM_WIKI_BASE_DIR", str(base))
    os.execvpe(str(py), [str(py), str(script)], env)


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

    Examples:
        llm-wiki translate enable --lang vi
        llm-wiki translate enable --lang vi --lang ja
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
    """Disable auto-translation. Giữ list langs để enable lại sau.

    Examples:
        llm-wiki translate disable
    """
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
    """In trạng thái auto-translation hiện tại.

    Examples:
        llm-wiki translate status
    """
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

    Examples:
        llm-wiki translate check --lang vi
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


def _collect_config(cfg: dict, raw: dict, prefix: str = "") -> list[tuple]:
    """Flatten effective config thành rows cho `_ui.config_table`.

    Row ("section", name) hoặc ("row", path, value_repr, source_label, source_style).
    """
    rows: list[tuple] = []
    for k, v in cfg.items():
        path = prefix + k
        if isinstance(v, dict):
            rows.append(("section", path))
            rows.extend(_collect_config(
                v, raw.get(k, {}) if isinstance(raw.get(k), dict) else {}, path + "."))
            continue
        env_name = _ENV_KEYS.get(tuple(path.split(".")))
        shown, from_env = (v, False)
        if env_name:
            shown, from_env = _env_effective(env_name, v)
        if from_env:
            label, style = f"env {env_name}", "yellow"
        elif k in raw:
            label, style = "toml", "cyan"
        else:
            label, style = "default", "dim"
        rows.append(("row", path, f"{shown!r}", label, style))
    return rows


@config_app.command("show")
def config_show(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd).",
    ),
) -> None:
    """In effective config: builtin defaults + .llm-wiki.toml + env override.

    Mỗi dòng đánh dấu nguồn: [default] / [toml] / [env ...].

    Examples:
        llm-wiki config show
        llm-wiki config show --root /path/to/wiki
    """
    from llm_wiki.config_file import get_config, load
    cfg = get_config(root)
    raw = load(root)
    if not raw:
        console.print("[dim](.llm-wiki.toml không tồn tại — dùng toàn bộ defaults)[/dim]\n")
    _ui.config_table(_collect_config(cfg, raw))
    console.print()
    console.print("Đổi giá trị: sửa [cyan].llm-wiki.toml[/cyan] ở wiki root (env var override khi set).")


# ─────────────────────────────────────────────────────────────────────────────
# Verify (human duyệt artifact — cả personal + project)
# ─────────────────────────────────────────────────────────────────────────────


@check_app.command("verify")
@app.command("verify", hidden=True)
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

    Examples:
        llm-wiki check verify wiki/tech/concept/x.md --by nihmtaho
        llm-wiki check verify wiki/tech/concept/x.md --unverify
    """
    if not unverify and not by:
        _ui.err_panel("thiếu --by (human id duyệt). Dùng --unverify để xoá verified.",
                      "llm-wiki check verify <path> --by <id>")
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
        _ui.err_panel(f"{e}", "llm-wiki check verify --help")
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Proposals — duyệt staging edits của AI (wiki/.proposals/)
# ─────────────────────────────────────────────────────────────────────────────


@review_app.command("list")
@_alias_proposals_app.command("list", hidden=True)
def proposals_list(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """Liệt kê đề xuất đang chờ duyệt + độ lớn diff so với page hiện tại.

    Examples:
        llm-wiki review list
    """
    _run_base_tool("proposals.py", ["list"], root)


@review_app.command("show")
@_alias_proposals_app.command("show", hidden=True)
def proposals_show(
    name: str = typer.Argument(..., help="Tên proposal (hoặc một phần, nếu duy nhất)."),
    context: int = typer.Option(3, "--context", "-C", help="Số dòng ngữ cảnh quanh diff."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """In metadata + unified diff của proposal so với page đích hiện tại.

    Examples:
        llm-wiki review show my-proposal
        llm-wiki review show my-proposal --context 5
    """
    _run_base_tool("proposals.py", ["show", name, "--context", str(context)], root)


@review_app.command("apply")
@_alias_proposals_app.command("apply", hidden=True)
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
    page vẫn unverified và bạn duyệt sau bằng `llm-wiki check verify`.

    Examples:
        llm-wiki review apply my-proposal
        llm-wiki review apply my-proposal --by nihmtaho
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
                      f"`llm-wiki check verify <path> --by {by}`")
        return
    from llm_wiki import verify as verify_mod
    try:
        p = verify_mod.set_verified(root, applied, by)
        console.print(f"[green]✓[/green] verified (human-reviewed) → {p}")
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[yellow]![/yellow] apply OK nhưng không set verified được: {e}")
        console.print(f"  Tự chạy: llm-wiki check verify <path> --by {by}")


@review_app.command("new")
@_alias_proposals_app.command("new", hidden=True)
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
    """Tạo 1 proposal STAGING (không sửa page). Cùng format MCP `wiki_propose_edit`.

    Examples:
        echo "new content" | llm-wiki review new --target wiki/tech/concept/x.md
        llm-wiki review new --target wiki/tech/concept/x.md --file /tmp/draft.md --by opencode
    """
    args = ["new", "--target", target, "--file", file, "--by", by, "--note", note]
    _run_base_tool("proposals.py", args, root)


@review_app.command("discard")
@_alias_proposals_app.command("discard", hidden=True)
def proposals_discard(
    name: str = typer.Argument(..., help="Tên proposal."),
    force: bool = typer.Option(False, "--force", "-f", help="Xác nhận xoá."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """Từ bỏ 1 proposal (xoá file, không ghi gì vào wiki).

    Examples:
        llm-wiki review discard my-proposal --force
    """
    args = ["discard", name]
    if force:
        args.append("--force")
    _run_base_tool("proposals.py", args, root)


# ─────────────────────────────────────────────────────────────────────────────
# Doctor
# ─────────────────────────────────────────────────────────────────────────────


_SKILL_LAYER = [
    ("ingest ra wiki page", "llm-wiki-ingest",
     "`llm-wiki wiki ingest` chỉ INDEX 1 file vào DB; người VIẾT page là skill."),
    ("trả lời câu hỏi + rerank", "llm-wiki-query",
     "retrieval là MCP/CLI, nhưng chấm ứng viên và tổng hợp trả lời là LLM của AI tool."),
    ("review ngữ nghĩa (mâu thuẫn, stale)", "llm-wiki-review",
     "`llm-wiki check lint` chỉ kiểm cấu trúc tất định."),
    ("consolidate / gộp concept", "llm-wiki-consolidate", "additive merge + distill-verify."),
    ("dịch page", "llm-wiki-translate",
     "`llm-wiki translate enable` chỉ ghi config; bản dịch do skill tạo."),
    ("research xuyên wiki", "llm-wiki-research", "cài ở root codebase, không nằm trong wiki."),
]


@setup_app.command("doctor")
@app.command("doctor", hidden=True)
def doctor_cmd(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root cần kiểm (mặc định $WIKI_ROOT hoặc cwd)."),
) -> None:
    """Kiểm tra môi trường: base runtime, tools lệch, deps, registry, wiki hiện tại.

    Báo rõ phần nào FAIL (chặn dùng), phần nào WARN (chạy được nhưng mất tính năng),
    và ranh giới CLI-vs-skill (việc gì bắt buộc phải có AI tool).

    Examples:
        llm-wiki setup doctor
        llm-wiki setup doctor --root /path/to/wiki
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

    _ui.section("Môi trường")
    if base.exists():
        ok(f"base runtime: {base}")
    else:
        fail(f"base runtime chưa cài: {base} → chạy `llm-wiki setup tools`")
    py = get_base_python()
    ok(f"base python: {py}") if py.exists() else fail(f"thiếu venv python: {py} → `llm-wiki setup tools --force`")

    src_tools = package_path("base_tools")
    if src_tools.is_dir() and (base / "tools").is_dir():
        stale = sorted(f.name for f in src_tools.glob("*.py")
                       if not (base / "tools" / f.name).exists()
                       or (base / "tools" / f.name).read_bytes() != f.read_bytes())
        if stale:
            warn(f"tools/ trong base LỆCH với package ({len(stale)} file) → chạy "
                 f"`llm-wiki setup tools`: {', '.join(stale[:6])}")
        else:
            ok("tools/ đồng bộ với package")

    _ui.section("Dependencies (base venv)")
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

    _ui.section("Registry")
    from llm_wiki.registry import list_wikis
    wikis = list_wikis()
    ok(f"{len(wikis)} wiki đã đăng ký") if wikis else warn(
        "registry rỗng → MCP không thấy wiki nào; chạy `llm-wiki setup`")
    for w in wikis:
        if not Path(w.get("path", "")).exists():
            fail(f"'{w.get('name')}' trỏ tới path không còn tồn tại: {w.get('path')} "
                 f"→ `llm-wiki wiki remove {w.get('name')}`")
        if not w.get("id"):
            warn(f"'{w.get('name')}' chưa có id (UUID) — thêm lại bằng `llm-wiki wiki add`")

    _ui.section("Wiki hiện tại")
    cfg = root / ".llm-wiki.toml"
    if cfg.is_file():
        ok(f".llm-wiki.toml: {cfg}")
        from llm_wiki.config_file import load as load_cfg
        prof = (load_cfg(root).get("wiki") or {}).get("profile")
        ok(f"\\[wiki].profile = {prof}") if prof else warn(
            "thiếu \\[wiki].profile → skill không biết đang ở chế độ nào; chạy lại "
            "`llm-wiki setup personal|project` (nó idempotent)")
    else:
        warn(f"không có .llm-wiki.toml ở {root} (dùng defaults; đây có phải wiki root?)")
    if wikis and not any(Path(w.get("path", "")).resolve() == Path(root).resolve()
                         for w in wikis):
        warn(f"{root} CHƯA đăng ký trong registry → MCP không tìm thấy nó qua `wiki=`")
    props = list((root / "wiki" / ".proposals").glob("*")) if (root / "wiki" / ".proposals").is_dir() else []
    props = [p for p in props if p.is_file() and not p.name.startswith(".")]
    if props:
        warn(f"{len(props)} proposal đang chờ duyệt → `llm-wiki review list`")
    else:
        ok("không có proposal tồn đọng")

    _ui.section("Việc cần AI tool (CLI không tự làm)")
    console.print("  llm-wiki KHÔNG gọi LLM. Các bước sinh nội dung chạy bằng LLM của")
    console.print("  AI tool đang mở, qua skill đã cài ở .agents/skills/:")
    _ui.skill_table(_SKILL_LAYER)

    if fails:
        _ui.done_panel(f"doctor: {len(fails)} lỗi, {len(warns)} cảnh báo",
                       [f"[red]✗[/red] {m}" for m in fails], ok_style=False)
        raise typer.Exit(1)
    _ui.done_panel(f"doctor: OK" + (f" — {len(warns)} cảnh báo" if warns else ""),
                   [f"[yellow]![/yellow] {m}" for m in warns] or ["Không có lỗi."])


def main() -> None:
    """Guarded entry point: user errors already exited; unexpected ones get a panel."""
    try:
        app()
    except (typer.Exit, typer.Abort):
        raise
    except Exception as exc:  # noqa: BLE001 — last-resort guard, spec §8
        if "--mcp" in sys.argv or _ui.is_debug():
            raise
        _ui.err_panel(f"Unexpected error: {exc}", "llm-wiki --debug <same command> for traceback")
        raise typer.Exit(1)


if __name__ == "__main__":
    main()
