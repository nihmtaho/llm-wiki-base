"""llm-wiki CLI — Typer app.

Subcommands (canonical):
    setup personal   — init personal knowledge wiki in-place (data only + MCP + registry)
    setup project    — init project wiki + install centralized MCP per-project + register
    setup tools      — install global runtime to ~/.llm-wiki-base/ (once per machine)
    setup doctor     — check environment + show which commands need an AI tool
    wiki ingest      — wrapper: call global tools/ingest.py with cwd context
    wiki reindex     — wrapper: rebuild search DB + RAG (--full | --check)
    check lint       — wrapper: health check (--fix for safe fixes)
    check verify     — human reviews artifact: set/clear `verified` in page frontmatter
    check eval       — wrapper: measure retrieval on golden queries P@k/R@k/MRR (--compare)
    review ...       — review AI staging edits: list / show (diff) / apply / discard
    watch            — wrapper: daemon scanning inbox + ingest + reindex
    serve --mcp      — run centralized MCP server (stdio) for AI tools
    translate        — enable/disable/status/check (TRANSLATING is the skill's job, not CLI)
    config show      — print effective config (defaults + .llm-wiki.toml + env overrides)

Every command above is DETERMINISTIC. llm-wiki never calls an LLM: content
generation (ingest into pages, review, consolidate, translate, rerank) is done
by SKILLS running on the LLM of the AI tool you have open.
`llm-wiki setup doctor` lists exactly that boundary when you are unsure.
"""
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import typer
from rich.prompt import Confirm, Prompt

from llm_wiki import __version__, _ui
from llm_wiki._ui import console
from llm_wiki.base import get_base_dir, get_base_python, install_base

app = typer.Typer(
    name="llm-wiki",
    help="LLM-maintained wiki with hybrid BM25+vector search, centralized MCP bridge, multi-base init.",
    no_args_is_help=True,
    add_completion=False,
)

# Hidden pre-redesign group (spec §7): no callback — bare `llm-wiki init`
# shows init help, `init personal|project` still work as hidden aliases.
# The wizard lives at `setup` (setup_interactive) since Task 7.
init_app = typer.Typer(
    help="Init a new wiki (personal or project)",
    hidden=True,
    epilog="Examples:\n  llm-wiki init\n  llm-wiki setup personal --name notes --no-mcp",
)

setup_app = typer.Typer(
    help="Set up wikis, tools and health checks",
    epilog="Examples:\n  llm-wiki setup\n  llm-wiki setup personal --name notes --yes",
)
wiki_app = typer.Typer(help="Manage wikis in the centralized MCP registry")
check_app = typer.Typer(help="Check wiki health: lint, verify, eval")
review_app = typer.Typer(help="Review AI-proposed wiki edits (wiki/.proposals/)")
translate_app = typer.Typer(help="Translate wiki pages into other languages")
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
    _ui.banner("llm-wiki setup", "Create a new wiki in 3 questions.")
    wtype = Prompt.ask("Wiki type", choices=["personal", "project"], default="personal")
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
        "Wiki language (the agent will write pages in this language)", default=lang)
    skills_target = Prompt.ask(
        "Skills target", choices=["universal", "claude", "both", "skip"],
        default=skills_target)
    do_mcp = Confirm.ask("Install MCP into the wiki?", default=not skip_mcp)
    return lang, skills_target, not do_mcp


def _confirm_and_run_personal(cwd: Path, name: str | None, lang: str,
                              clients: list[str], skills_target: str,
                              skip_mcp: bool, yes: bool, register: bool = True,
                              force: bool = False) -> None:
    from llm_wiki.init_personal import run as run_personal
    facts = [
        "Type:     personal",
        f"Name:     {name or cwd.name}",
        f"Path:     {cwd}",
        f"Lang:     {lang}",
        f"Clients:  {', '.join(clients) if clients else '(none)'}",
        f"Skills:   {skills_target}",
        f"MCP:      {'skip' if skip_mcp else 'install'}",
    ]
    _ui.ok_panel("Ready to create", facts)
    if not (yes or force) and not Confirm.ask("Create wiki?", default=True):
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
        "Type:     project",
        f"Root:     {root}",
        f"Subdir:   {wiki_subdir}",
        f"Lang:     {lang}",
        f"Clients:  {', '.join(clients) if clients else '(none)'}",
        f"Skills:   {skills_target}",
        f"MCP:      {'skip' if skip_mcp else 'install'}",
        f"Server:   {server_name}",
    ]
    _ui.ok_panel("Ready to create", facts)
    if not (yes or force) and not Confirm.ask("Create wiki?", default=True):
        raise typer.Exit(0)
    run_project(root=root, wiki_subdir=wiki_subdir, clients=clients,
                server_name=server_name, force=True, skills_target=skills_target,
                skip_mcp=skip_mcp, lang=lang, register=register)


def _slim_personal() -> None:
    """Q1 location (name) → Q3 clients; lang/skills/MCP use fixed defaults
    (extras only via `setup personal|project --interactive`)."""
    cwd = Path.cwd()
    name = Prompt.ask("Wiki name", default=cwd.name)
    clients = _parse_clients(Prompt.ask(
        "AI clients for MCP install (comma-separated)", default="claude"))
    _validate_clients(clients)
    lang, skills_target, skip_mcp = "en", "universal", False
    _confirm_and_run_personal(cwd, name, lang, clients, skills_target, skip_mcp, yes=False)


def _slim_project() -> None:
    """Q1 location (root + subdir) → Q3 clients; lang/skills/MCP use fixed defaults
    (extras only via `setup personal|project --interactive`)."""
    root = Path(Prompt.ask("Project root", default=str(Path.cwd()))).resolve()
    wiki_subdir = Prompt.ask("Wiki subdir (under project root)", default="project-wiki")
    clients = _parse_clients(Prompt.ask(
        "AI clients for MCP install (comma-separated)", default="claude"))
    _validate_clients(clients)
    lang, skills_target, skip_mcp = "en", "universal", False
    _confirm_and_run_project(root, wiki_subdir, lang, clients, skills_target, skip_mcp, yes=False)


@setup_app.command("personal")
@init_app.command("personal", hidden=True)
def init_personal(
    here: bool = typer.Option(True, "--here", help="Init at cwd (in-place)."),
    name: str | None = typer.Option(None, "--name", "-n", help="Wiki name (default: folder name)."),
    lang: str | None = typer.Option(
        None, "--lang", "-l",
        help="Wiki language written to [wiki].lang (e.g. vi, en). The agent writes pages in this language.",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation when the dir has content."),
    client: list[str] = typer.Option(
        ["claude"], "--client", "-c",
        help="AI client for the centralized MCP: claude | opencode | zed | commandcode. "
             "Repeat: -c claude -c commandcode.",
    ),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Skip MCP install into the per-project/personal wiki."),
    skills_target: str = typer.Option(
        "universal", "--skills-target",
        help="Where to install skills: 'universal' = <wiki>/.agents/skills/ (canonical, "
             "Claude/OpenCode symlinked in); 'claude' = also symlink .claude/skills/; 'both' = + "
             ".opencode/commands/; 'skip'.",
    ),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip skill install."),
    no_register: bool = typer.Option(
        False, "--no-register",
        help="Skip writing this wiki to registry.toml (tests/scripts — keeps the real registry clean).",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip the confirmation screen (scripts/CI). Never prompts.",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i",
        help="Ask for lang, skills target, and skip-MCP before the confirmation screen.",
    ),
) -> None:
    """Init one personal knowledge wiki at cwd. In-place. Installs MCP + registry by default.

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
            "AI clients for MCP install (comma-separated)",
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
        help="Subfolder under the project root to hold wiki data.",
    ),
    lang: str | None = typer.Option(
        None, "--lang", "-l",
        help="Wiki language written to [wiki].lang (e.g. vi, en).",
    ),
    client: list[str] = typer.Option(
        ["claude"], "--client", "-c",
        help="AI client for the centralized MCP: claude | opencode | zed | commandcode.",
    ),
    server_name: str = typer.Option(
        "llm-wiki-base-mcp", "--server-name", "-s",
        help="Centralized MCP server name (shared across all wikis on this machine).",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation when the wiki subdir has content."),
    skills_target: str = typer.Option(
        "universal", "--skills-target",
        help="Where to install skills: 'universal' (canonical .agents/skills/ + client links), "
             "'claude', 'both', 'skip'.",
    ),
    no_skills: bool = typer.Option(False, "--no-skills", help="Skip skill install."),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Skip MCP install into the per-project wiki."),
    no_register: bool = typer.Option(
        False, "--no-register",
        help="Skip writing this wiki to registry.toml (tests/scripts — keeps the real registry clean).",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip the confirmation screen (scripts/CI). Never prompts.",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i",
        help="Ask for lang, skills target, and skip-MCP before the confirmation screen.",
    ),
) -> None:
    """Init a project wiki: create <root>/<wiki-dir>/ + TOML register + per-project MCP + skills.

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
            "AI clients for MCP install (comma-separated)",
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
    """List all wikis in the centralized MCP registry.

    Examples:
        llm-wiki wiki list
    """
    from llm_wiki.registry import list_wikis
    wikis = list_wikis()
    if not wikis:
        if _ui.is_quiet():
            return
        console.print("[dim]Registry is empty. Run `llm-wiki setup` to create your first wiki.[/dim]")
        return
    _ui.wiki_table(wikis)
    if any(not w.get("id") for w in wikis):
        console.print("[dim]Empty ID → re-run `llm-wiki wiki add`.[/dim]")
    console.print()
    console.print("AI tools pass `wiki=<name>` to target one wiki "
                  "(also accepts `id`).")
    console.print("Leave `wiki=` empty to search cross-wiki (including personal wikis).")
    console.print("[dim]Same name + different path → init auto-suffixes -<uuid8>, "
                  "no eviction.[/dim]")


@wiki_app.command("add")
def wiki_add_cmd(
    name: str = typer.Argument(..., help="Wiki name (used as the identifier in MCP)."),
    path: str = typer.Argument(..., help="Absolute path to the wiki root."),
    type: str = typer.Option("personal", "--type", "-t", help="personal or project."),
) -> None:
    """Register an existing wiki into the centralized MCP registry.

    Examples:
        llm-wiki wiki add notes /path/to/notes
        llm-wiki wiki add docs /path/to/repo/project-wiki --type project
    """
    from llm_wiki.registry import add_wiki
    wiki_path = Path(path).resolve()
    if not wiki_path.exists():
        _ui.err_panel(f"path does not exist: {wiki_path}", "llm-wiki wiki list")
        raise typer.Exit(1)
    used = add_wiki(name, str(wiki_path), wiki_type=type)
    if used != name:
        console.print(f"[yellow]![/yellow] name '{name}' is taken by another wiki "
                      f"(different path) → registered as '{used}'")
    console.print(f"[green]✓[/green] registered: '{used}' (type={type}) → {wiki_path}")


@wiki_app.command("remove")
def wiki_remove_cmd(
    name: str = typer.Argument(..., help="Wiki name OR id to remove from the registry."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation."),
) -> None:
    """Remove one wiki from the registry (files are kept).

    Examples:
        llm-wiki wiki remove notes
        llm-wiki wiki remove notes --force
    """
    from llm_wiki.registry import find, remove_wiki
    if not find(name):
        _ui.err_panel(f"wiki '{name}' is not in the registry", "llm-wiki wiki list")
        raise typer.Exit(1)
    if not force:
        if not Confirm.ask(f"Remove '{name}' from the registry? (files are kept)"):
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
        help="Target dir (default: ~/.llm-wiki-base). Override via LLM_WIKI_BASE_DIR env.",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Recreate venv + reinstall requirements."),
) -> None:
    """Install the global llm-wiki-base runtime (tools/, rag/, scripts/, .venv/).

    Run once after `pip install llm-wiki`. Idempotent — re-run to sync the
    newest tools/rag/scripts from the package, including the centralized MCP server.

    Examples:
        llm-wiki setup tools
        llm-wiki setup tools --force
        llm-wiki setup tools --dir ~/.llm-wiki-base
    """
    base = install_base(base_dir=dir, force=force)
    _ui.done_panel("llm-wiki-base installed",
                   [f"at:     {base}", f"python: {get_base_python()}"])
    console.print()
    console.print("Next: cd into an empty folder, then `llm-wiki setup personal` to create wiki data + MCP.")


@config_app.command("path")
@_alias_base_app.command("path", hidden=True)
def base_path() -> None:
    """Print the current global base path (env override or default).

    Examples:
        llm-wiki config path
    """
    console.print(get_base_dir())


# ─────────────────────────────────────────────────────────────────────────────
# Per-wiki wrappers (gọi global tools/ với cwd context)
# ─────────────────────────────────────────────────────────────────────────────


def _run_base_tool(tool_name: str, args: list[str], wiki_root: Path,
                   capture: bool = False) -> tuple[int, str]:
    """Run one script from the global base in the wiki's context.

    Returns (exit_code, stdout). `capture=False` → print straight to console (legacy).

    Never leak subprocess tracebacks to the user: `check_call` throws a bare
    CalledProcessError on tool failure (with the CLI's Python stack, saying nothing
    about the wiki). Here we forward the tool's exit code + the next step hint.
    """
    base = get_base_dir()
    py = get_base_python()
    script = base / "tools" / tool_name
    if not script.exists():
        _ui.err_panel(f"{script} does not exist.", "llm-wiki setup tools")
        raise typer.Exit(1)
    if not Path(py).exists():
        _ui.err_panel(f"missing base venv python: {py}", "llm-wiki setup tools --force")
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
                      f"failed (exit {e.returncode}).",
                      "llm-wiki wiki reindex --check, then llm-wiki setup doctor")
        raise typer.Exit(e.returncode or 1)
    except FileNotFoundError:
        _ui.err_panel(f"cannot run {py} — broken base venv?",
                      "llm-wiki setup tools --force")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        raise typer.Exit(130)


@wiki_app.command("ingest")
@app.command("ingest", hidden=True)
def ingest_cmd(
    path: str = typer.Argument(..., help="Source path relative to the wiki root (e.g. raw/inbox/foo.md)."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Index one source into the search DB. Does NOT write a wiki page — that is
    the ingest skill's job. Run from inside the wiki dir.

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
    full: bool = typer.Option(False, "--full", help="Rebuild from scratch (ignore content-hash). Required after changing embed_model/chunk_tokens/vector."),
    check: bool = typer.Option(False, "--check", help="Dry-run: report what would index/delete + config drift, write NOTHING."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Rebuild the search DB + RAG index. Incremental by content-hash by default.

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
    fix: bool = typer.Option(False, "--fix", help="Safe fixes: drop dangling rows + add missing index entries."),
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
    k: int = typer.Option(0, "--k", help="Metric cutoff (default: [eval].k, then top_n_final)."),
    compare: bool = typer.Option(False, "--compare", help="Compare profiles: tier1-weighted / rrf-text / rrf+vector."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON instead of a table."),
    init: bool = typer.Option(False, "--init", help="Create eval/golden.toml from the template."),
    no_save: bool = typer.Option(False, "--no-save", help="Do not append to eval/results.json."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print per-query numbers."),
    root: Path = typer.Option(Path.cwd(), "--root", "-r", help="Wiki root (default: cwd)."),
) -> None:
    """Measure retrieval quality on the golden query set (P@k / R@k / MRR).

    Read-only on the wiki: never edits markdown, never writes wiki/log.md.

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
    """Daemon: scan raw/inbox/ → ingest → reindex → lint. Run from inside the wiki dir.

    Examples:
        llm-wiki watch
        llm-wiki watch --root /path/to/wiki
    """
    _run_base_tool("watch.py", [], root)


@_tail_app.command("serve")
def serve_cmd(
    mcp: bool = typer.Option(False, "--mcp", help="Run the centralized MCP server (stdio)."),
) -> None:
    """Run the MCP server for AI tools — same as `llm-wiki serve --mcp`.

    Execs the base python + tools/mcp_base_server.py (keeps the venv that has
    stdio pass-through for JSON-RPC). The MCP entry in the per-project wiki file
    points at this command: ["llm-wiki", "serve", "--mcp"].

    Examples:
        llm-wiki serve --mcp
    """
    if not mcp:
        _ui.err_panel("`llm-wiki serve` needs flag --mcp (stdio MCP server for AI tools).",
                      "llm-wiki serve --mcp")
        raise typer.Exit(2)
    from llm_wiki.installer import CENTRALIZED_SERVER_SCRIPT
    base = get_base_dir()
    script = base / "tools" / CENTRALIZED_SERVER_SCRIPT
    py = get_base_python()
    if not script.exists():
        _ui.err_panel(f"{script} does not exist.", "llm-wiki setup tools")
        raise typer.Exit(1)
    if not Path(py).exists():
        _ui.err_panel(f"missing base venv python: {py}", "llm-wiki setup tools --force")
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
        help="Target language code (e.g. vi, ja, fr). Repeatable: -l vi -l ja.",
    ),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (default: $WIKI_ROOT or cwd).",
    ),
) -> None:
    """Enable auto-translation. Writes target langs to `.llm-wiki.toml` at the wiki root.

    After enabling, the ingest skill auto-calls the `llm-wiki-translate` skill to
    translate each new source into the target langs (using the running AI tool's LLM).

    Examples:
        llm-wiki translate enable --lang vi
        llm-wiki translate enable --lang vi --lang ja
    """
    from llm_wiki.config_file import set_translate
    p = set_translate(root, enabled=True, langs=lang)
    console.print(f"[green]✓[/green] enabled → {', '.join(sorted(set(lang)))}")
    console.print(f"  written to: {p}")
    console.print()
    console.print("From now on, ingest auto-creates <slug>.<lang>.md for each new page.")
    console.print("Translations do NOT enter the DB/RAG (skip rule *.lang.md).")


@translate_app.command("disable")
def translate_disable(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (default: $WIKI_ROOT or cwd).",
    ),
) -> None:
    """Disable auto-translation. Keeps the lang list for re-enabling later.

    Examples:
        llm-wiki translate disable
    """
    from llm_wiki.config_file import get_translate_config, set_translate
    _, langs = get_translate_config(root)
    set_translate(root, enabled=False, langs=langs)
    if langs:
        console.print(f"[green]✓[/green] disabled (langs kept: {langs}). Re-enable with `llm-wiki translate enable`.")
    else:
        console.print("[green]✓[/green] disabled.")


@translate_app.command("status")
def translate_status(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (default: $WIKI_ROOT or cwd).",
    ),
) -> None:
    """Print the current auto-translation status.

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
    lang: str = typer.Option(..., "--lang", "-l", help="Language code to verify."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (default: $WIKI_ROOT or cwd).",
    ),
) -> None:
    """Verify every <slug>.md has a matching <slug>.<lang>.md with the same frontmatter keys + heading structure.

    Needs no LLM — only reads files + compares structure.

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
_ENV_CAST: dict[str, Callable[[str], object]] = {
    "WIKI_BM25_WEIGHT": float,
    "WIKI_VEC_WEIGHT": float,
    "WIKI_CHUNK_BM25": lambda s: s.strip().lower() not in ("0", "false", "no", "off"),
}


def _env_effective(env_name: str, current):
    """The effective value when this env is set (mirrors config_file.effective)."""
    raw = os.environ.get(env_name)
    if raw is None or raw == "":
        return current, False
    cast = _ENV_CAST.get(env_name)
    if cast is None:
        return raw, True
    try:
        return cast(raw), True
    except (ValueError, AttributeError):
        return f"{raw} (unparsable)", True


def _collect_config(cfg: dict, raw: dict, prefix: str = "") -> list[tuple]:
    """Flatten the effective config into rows for `_ui.config_table`.

    Row ("section", name) or ("row", path, value_repr, source_label, source_style).
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
        help="Wiki root (default: $WIKI_ROOT or cwd).",
    ),
) -> None:
    """Print the effective config: builtin defaults + .llm-wiki.toml + env overrides.

    Each line is tagged with its source: [default] / [toml] / [env ...].

    Examples:
        llm-wiki config show
        llm-wiki config show --root /path/to/wiki
    """
    from llm_wiki.config_file import get_config, load
    cfg = get_config(root)
    raw = load(root)
    if not raw:
        console.print("[dim](no .llm-wiki.toml — using all defaults)[/dim]\n")
    _ui.config_table(_collect_config(cfg, raw))
    console.print()
    console.print("To change a value: edit [cyan].llm-wiki.toml[/cyan] at the wiki root (env vars override when set).")


# ─────────────────────────────────────────────────────────────────────────────
# Verify (human duyệt artifact — cả personal + project)
# ─────────────────────────────────────────────────────────────────────────────


@check_app.command("verify")
@app.command("verify", hidden=True)
def verify_cmd(
    path: str = typer.Argument(..., help="Page path relative to the wiki root (e.g. wiki/tech/concept/x.md)."),
    by: str | None = typer.Option(None, "--by", "-b", help="Reviewing human id (e.g. nihmtaho). Required when setting (not for --unverify). Stored as human:<id>."),
    unverify: bool = typer.Option(False, "--unverify", help="Drop the verified field (back to unverified)."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (default: $WIKI_ROOT or cwd).",
    ),
) -> None:
    """Human reviews an artifact: set/clear `verified` in the page frontmatter.

    Review = set verified → trust tier *human-reviewed*. Same mechanism for
    personal + project wikis. No LLM — deterministic frontmatter edit.

    Examples:
        llm-wiki check verify wiki/tech/concept/x.md --by nihmtaho
        llm-wiki check verify wiki/tech/concept/x.md --unverify
    """
    if not unverify and not by:
        _ui.err_panel("missing --by (reviewing human id). Use --unverify to drop verified.",
                      "llm-wiki check verify <path> --by <id>")
        raise typer.Exit(1)
    from llm_wiki import verify as verify_mod
    try:
        if unverify:
            p = verify_mod.unverify(root, path)
            console.print(f"[green]✓[/green] unverified → {p}")
        else:
            p = verify_mod.set_verified(root, path, by or "")
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
        help="Wiki root (default: $WIKI_ROOT or cwd)."),
) -> None:
    """List pending proposals + diff size against the current pages.

    Examples:
        llm-wiki review list
    """
    _run_base_tool("proposals.py", ["list"], root)


@review_app.command("show")
@_alias_proposals_app.command("show", hidden=True)
def proposals_show(
    name: str = typer.Argument(..., help="Proposal name (or a unique substring)."),
    context: int = typer.Option(3, "--context", "-C", help="Context lines around the diff."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (default: $WIKI_ROOT or cwd)."),
) -> None:
    """Print a proposal's metadata + unified diff against its current target page.

    Examples:
        llm-wiki review show my-proposal
        llm-wiki review show my-proposal --context 5
    """
    _run_base_tool("proposals.py", ["show", name, "--context", str(context)], root)


def parse_apply_output(out: str, target: str | None) -> str | None:
    """Extract the target path from `proposals.py apply` output.

    Precedence: explicit `--target` → JSON `RESULT {...}` line (new contract) →
    legacy `APPLIED\\t<rel>` line. Returns None when unreadable.
    """
    import json as _json
    import re as _re
    if target:
        return target
    for line in reversed((out or "").splitlines()):
        line = line.strip()
        if line.startswith("RESULT "):
            try:
                payload = _json.loads(line[len("RESULT "):])
            except ValueError:
                continue
            rel = payload.get("target") if isinstance(payload, dict) else None
            if rel:
                return str(rel)
    m = _re.search(r"^APPLIED\t(.+)$", out or "", _re.MULTILINE)
    return m.group(1).strip() if m else None


@review_app.command("apply")
@_alias_proposals_app.command("apply", hidden=True)
def proposals_apply(
    name: str = typer.Argument(..., help="Proposal name."),
    target: str | None = typer.Option(
        None, "--target", help="Force the target path (only needed for legacy proposals without metadata)."),
    by: str | None = typer.Option(
        None, "--by", "-b", help="Human id — when given, the page is set `verified` after apply."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (default: $WIKI_ROOT or cwd)."),
) -> None:
    """Accept one proposal: write to the target page + log + reindex + delete the proposal.

    `--by <id>` is YOUR signature (trust tier human-reviewed) — without it the
    page stays unverified and you review later with `llm-wiki check verify`.

    Examples:
        llm-wiki review apply my-proposal
        llm-wiki review apply my-proposal --by nihmtaho
    """
    args = ["apply", name]
    if target:
        args += ["--target", target]
    rc, out = _run_base_tool("proposals.py", args, root, capture=True)
    if rc != 0:
        raise typer.Exit(rc)
    if not by:
        return
    # proposals.py in `APPLIED\t<rel>` + dòng JSON `RESULT {...}` trước khi xoá
    # file — CLI cần target SAU khi proposal đã không còn trên đĩa.
    applied = parse_apply_output(out, target)
    if not applied:
        console.print("[yellow]![/yellow] cannot read the target path from output — review manually: "
                      f"`llm-wiki check verify <path> --by {by}`")
        return
    from llm_wiki import verify as verify_mod
    try:
        p = verify_mod.set_verified(root, applied, by)
        console.print(f"[green]✓[/green] verified (human-reviewed) → {p}")
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[yellow]![/yellow] applied OK but could not set verified: {e}")
        console.print(f"  Run manually: llm-wiki check verify <path> --by {by}")


@review_app.command("new")
@_alias_proposals_app.command("new", hidden=True)
def proposals_new(
    target: str = typer.Option(..., "--target", "-t",
                               help="Target page, relative inside the wiki (e.g. wiki/<domain>/concept/x.md)."),
    file: str = typer.Option("-", "--file", "-f",
                             help="File holding the proposed content; '-' = read from stdin."),
    by: str = typer.Option("", "--by", help="Who proposed it (tool/client) — stored in metadata."),
    note: str = typer.Option("", "--note", help="Reason for the proposal, shown in `show`."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (default: $WIKI_ROOT or cwd)."),
) -> None:
    """Create one STAGING proposal (touches no page). Same format as MCP `wiki_propose_edit`.

    Examples:
        echo "new content" | llm-wiki review new --target wiki/tech/concept/x.md
        llm-wiki review new --target wiki/tech/concept/x.md --file /tmp/draft.md --by opencode
    """
    args = ["new", "--target", target, "--file", file, "--by", by, "--note", note]
    _run_base_tool("proposals.py", args, root)


@review_app.command("discard")
@_alias_proposals_app.command("discard", hidden=True)
def proposals_discard(
    name: str = typer.Argument(..., help="Proposal name."),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm deletion."),
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root (default: $WIKI_ROOT or cwd)."),
) -> None:
    """Abandon one proposal (delete the file, write nothing to the wiki).

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
    ("ingest into wiki pages", "llm-wiki-ingest",
     "`llm-wiki wiki ingest` only INDEXES 1 file into the DB; the skill WRITES the page."),
    ("answer questions + rerank", "llm-wiki-query",
     "retrieval is MCP/CLI, but candidate scoring and answer synthesis need the AI tool's LLM."),
    ("semantic review (contradictions, stale)", "llm-wiki-review",
     "`llm-wiki check lint` only checks deterministic structure."),
    ("consolidate / merge concepts", "llm-wiki-consolidate", "additive merge + distill-verify."),
    ("translate pages", "llm-wiki-translate",
     "`llm-wiki translate enable` only writes config; the skill creates translations."),
    ("cross-wiki research", "llm-wiki-research", "installed at the codebase root, not inside a wiki."),
]


@setup_app.command("doctor")
@app.command("doctor", hidden=True)
def doctor_cmd(
    root: Path = typer.Option(
        Path(os.environ.get("WIKI_ROOT", ".")), "--root",
        help="Wiki root to check (default: $WIKI_ROOT or cwd)."),
) -> None:
    """Check the environment: base runtime, drifted tools, deps, registry, current wiki.

    Reports what FAILS (blocks usage), what WARNS (works with missing features),
    and the CLI-vs-skill boundary (what strictly needs an AI tool).

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

    _ui.section("Environment")
    if base.exists():
        ok(f"base runtime: {base}")
    else:
        fail(f"base runtime not installed: {base} → run `llm-wiki setup tools`")
    py = get_base_python()
    ok(f"base python: {py}") if py.exists() else fail(f"missing base venv python: {py} → `llm-wiki setup tools --force`")
    on_path = shutil.which("llm-wiki")
    if on_path:
        ok(f"llm-wiki on PATH: {on_path}")
    else:
        warn("`llm-wiki` not on PATH (it lives in the install venv's bin/) → symlink it "
             "into /usr/local/bin or export PATH; see README “Making `llm-wiki` available globally”")

    src_tools = package_path("base_tools")
    if src_tools.is_dir() and (base / "tools").is_dir():
        stale = sorted(f.name for f in src_tools.glob("*.py")
                       if not (base / "tools" / f.name).exists()
                       or (base / "tools" / f.name).read_bytes() != f.read_bytes())
        if stale:
            warn(f"base tools/ DRIFTED from the package ({len(stale)} files) → run "
                 f"`llm-wiki setup tools`: {', '.join(stale[:6])}")
        else:
            ok("tools/ in sync with the package")

    _ui.section("Dependencies (base venv)")
    # tomli CHỈ cần khi base venv là Python <3.11 (từ 3.11 có tomllib trong stdlib).
    py311 = True
    if py.exists():
        py311 = subprocess.run(
            [str(py), "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
            capture_output=True).returncode == 0
    checks = [("mcp", "MCP servers need this package"),
              ("fastembed", "the vector channel needs it (skippable when vector=false)")]
    if py311:
        ok("tomllib (Python ≥3.11 stdlib)")
    else:
        checks.append(("tomli", "Python <3.11 needs it to read .llm-wiki.toml"))
    for mod, why in checks:
        if not py.exists():
            break
        r = subprocess.run([str(py), "-c", f"import {mod}"], capture_output=True, text=True)
        if r.returncode == 0:
            ok(f"{mod}")
        elif mod == "fastembed":
            warn("fastembed missing → vector channel is off, `eval --compare` will report [ERROR]")
        else:
            fail(f"{mod} missing → `pip install -r {base}/requirements.txt` in the base venv ({why})")

    _ui.section("Registry")
    from llm_wiki.registry import list_wikis
    wikis = list_wikis()
    ok(f"{len(wikis)} wikis registered") if wikis else warn(
        "registry is empty → MCP sees no wikis; run `llm-wiki setup`")
    for w in wikis:
        if not Path(w.get("path", "")).exists():
            fail(f"'{w.get('name')}' points at a path that no longer exists: {w.get('path')} "
                 f"→ `llm-wiki wiki remove {w.get('name')}`")
        if not w.get("id"):
            warn(f"'{w.get('name')}' has no id (UUID) — re-add it with `llm-wiki wiki add`")

    _ui.section("Current wiki")
    cfg = root / ".llm-wiki.toml"
    if cfg.is_file():
        ok(f".llm-wiki.toml: {cfg}")
        from llm_wiki.config_file import load as load_cfg
        prof = (load_cfg(root).get("wiki") or {}).get("profile")
        ok(f"\\[wiki].profile = {prof}") if prof else warn(
            "missing \\[wiki].profile → skills cannot tell which mode this is; re-run "
            "`llm-wiki setup personal|project` (it is idempotent)")
    else:
        warn(f"no .llm-wiki.toml at {root} (using defaults; is this the wiki root?)")
    if wikis and not any(Path(w.get("path", "")).resolve() == Path(root).resolve()
                         for w in wikis):
        warn(f"{root} is NOT in the registry → MCP cannot find it via `wiki=`")
    props = list((root / "wiki" / ".proposals").glob("*")) if (root / "wiki" / ".proposals").is_dir() else []
    props = [p for p in props if p.is_file() and not p.name.startswith(".")]
    if props:
        warn(f"{len(props)} proposals awaiting review → `llm-wiki review list`")
    else:
        ok("no pending proposals")

    _ui.section("Needs an AI tool (CLI cannot do this)")
    console.print("  llm-wiki never calls an LLM. Content-generating steps run on the")
    console.print("  open AI tool's LLM, via skills installed at .agents/skills/:")
    _ui.skill_table(_SKILL_LAYER)

    if fails:
        _ui.done_panel(f"doctor: {len(fails)} errors, {len(warns)} warnings",
                       [f"[red]✗[/red] {m}" for m in fails], ok_style=False)
        raise typer.Exit(1)
    _ui.done_panel("doctor: OK" + (f" — {len(warns)} warnings" if warns else ""),
                   [f"[yellow]![/yellow] {m}" for m in warns] or ["No errors."])


# ─────────────────────────────────────────────────────────────────────────────
# Upgrade (GitHub tags vX.Y.Z → toàn bộ wikis trong registry)
# ─────────────────────────────────────────────────────────────────────────────


def _upgrade_root_suffix(r: dict, dry_run: bool) -> str:
    root = r.get("root")
    if not root:
        return ""
    if dry_run:
        return f" + root {root['path']} {root['old'] or '?'} → {root['new']} (codebase re-sync)"
    backup = f", backup {root['backup']}" if root["backup"] else ""
    return f" + root {root['path']} → {root['new']}{backup}"


@app.command("upgrade")
def upgrade_cmd(
    to: str = typer.Option("latest", "--to", help="Target tag (vX.Y.Z) or 'latest'."),
    wiki: str | None = typer.Option(None, "--wiki", help="Upgrade only this wiki (name or id)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show changes only, copy nothing."),
) -> None:
    """Upgrade wikis' skills + agent configs in the registry to a new tag.

    `project` wikis also get the `codebase` skill re-synced at the project root.

    Examples:
        llm-wiki upgrade --dry-run
        llm-wiki upgrade --to latest
        llm-wiki upgrade --to v0.2.0 --wiki my-wiki
    """
    from llm_wiki import upgrade as _upgrade

    core = _upgrade.find_core()
    if core is None:
        _ui.err_panel("No core checkout found (.git).",
                      "Run inside the llm-wiki-base repo or install core from git.")
        raise typer.Exit(2)
    tag = _upgrade.resolve_target(core, to)
    if tag is None:
        _ui.err_panel(f"Cannot resolve tag '{to}'.",
                      f"git -C {core} fetch --tags origin (offline?), "
                      "or the tag breaks the vX.Y.Z convention.")
        raise typer.Exit(1)
    if not dry_run and _upgrade.core_tag(core) != tag:
        _ui.err_panel(f"Core is not at {tag} — new files come from the running core.",
                      f"git -C {core} fetch --tags && git -C {core} checkout {tag} "
                      "(+ reinstall the package unless using pip install -e .)")
        raise typer.Exit(1)
    result = _upgrade.upgrade_all(core, tag, wiki_name=wiki, dry_run=dry_run)
    if result["unknown"]:
        _ui.err_panel(f"No wiki '{wiki}' in the registry.", "llm-wiki wiki list")
        raise typer.Exit(1)
    if dry_run:
        rows = []
        for r in result["done"]:
            changed = r["changed"]
            if changed is None:
                detail = "full re-sync (no VERSION yet)"
            elif not changed:
                detail = "already at this tag"
            else:
                detail = ", ".join(changed[:8]) + ("…" if len(changed) > 8 else "")
            rows.append(f"[cyan]{r['name']}[/cyan] {r['old'] or '?'} → {tag}: "
                        f"{detail}{_upgrade_root_suffix(r, True)}")
        for name in result["missing"]:
            rows.append(f"[yellow]![/yellow] {name}: path gone, skipped")
        _ui.done_panel(f"upgrade --dry-run → {tag}", rows or ["No wikis."])
        return
    rows = []
    for r in result["done"]:
        backup = f", backup {r['backup']}" if r["backup"] else ", nothing to back up"
        rows.append(f"[green]✓[/green] {r['name']} {r['old'] or '?'} → {tag}{backup}"
                    f"{_upgrade_root_suffix(r, False)}")
    for name in result["missing"]:
        rows.append(f"[yellow]![/yellow] {name}: path gone, skipped")
    _ui.done_panel(f"upgrade → {tag}", rows or ["No wikis."])


@app.command("status")
def status_cmd() -> None:
    """Core local/latest + VERSION of every wiki in the registry.

    Examples:
        llm-wiki status
    """
    from llm_wiki import registry
    from llm_wiki import upgrade as _upgrade

    core = _upgrade.find_core()
    if core is None:
        _ui.err_panel("No core checkout found (.git).",
                      "Run inside the llm-wiki-base repo or install core from git.")
        raise typer.Exit(2)
    latest = _upgrade.latest_tag(core)
    console.print(f"core: {core}")
    console.print(f"core tag: {_upgrade.core_tag(core) or '?'} / latest: {latest or '?'}")
    for w in registry.list_wikis():
        path = Path(w.get("path", "")).expanduser()
        ver = _upgrade.read_version(path) if path.is_dir() else None
        flag = "" if ver == latest else "  [yellow](old)[/yellow]"
        console.print(f"  [cyan]{w.get('name')}[/cyan]: {ver or '?'}{flag}")


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
