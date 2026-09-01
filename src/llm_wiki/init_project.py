"""Init flow cho project wiki.

Usage:
    llm-wiki init project [--root <dir>] [--wiki-dir <name>] [--client claude] [--server-name <name>] [--skills-target universal|claude|both] [--no-skills]

Tạo <root>/<wiki-dir>/ chứa data (wiki, raw, rag) + cài MCP config globally +
copy skills vào <wiki_dir>/.agents/skills/ (per-wiki).

Runtime code (tools/, rag/, scripts/, .venv/) ở global `~/.llm-wiki-base/`.
Project wiki chỉ chứa data + .env + .llm-wiki.toml + .agents/skills/.
"""
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

from llm_wiki._package_data import read_template, template_exists
from llm_wiki._skills import install_skills
from llm_wiki.base import get_base_dir, get_base_python
from llm_wiki.config import supported_clients
from llm_wiki.installer import install_mcp_config

console = Console()

AGENT_CONFIGS = ["_schema.md", "AGENTS.md", "CLAUDE.md"]


def _copy_agent_configs(cwd: Path) -> list[str]:
    """Copy agent config templates (_schema.md, AGENTS.md, CLAUDE.md) to wiki root."""
    copied: list[str] = []
    for name in AGENT_CONFIGS:
        if not template_exists("templates", "agents", name):
            continue
        dst = cwd / name
        if dst.exists():
            continue
        dst.write_text(read_template("templates", "agents", name), encoding="utf-8")
        copied.append(name)
    return copied


def run(
    root: Path,
    wiki_subdir: str,
    clients: list[str],
    server_name: str,
    force: bool = False,
    skills_target: str = "universal",
) -> None:
    wiki_dir = (root / wiki_subdir).resolve()
    base_dir = get_base_dir()

    if not base_dir.exists():
        console.print(f"[red]Error:[/red] Global base chưa cài: {base_dir}")
        console.print(f"  Chạy trước: [cyan]llm-wiki base install[/cyan]")
        raise SystemExit(1)

    console.print(f"[bold]Init project wiki:[/bold]")
    console.print(f"  project root  : [cyan]{root}[/cyan]")
    console.print(f"  wiki subdir   : [cyan]{wiki_dir}[/cyan]")
    console.print(f"  base runtime  : [cyan]{base_dir}[/cyan]")
    console.print(f"  clients       : {', '.join(clients)}")
    console.print(f"  MCP server    : {server_name}")
    console.print()

    # Validate clients
    for c in clients:
        if c not in supported_clients():
            console.print(f"[red]Error:[/red] unknown client '{c}'. Supported: {supported_clients()}")
            raise SystemExit(1)

    # Check wiki_dir
    if wiki_dir.exists() and any(wiki_dir.iterdir()) and not force:
        if not Confirm.ask(
            f"{wiki_dir} đã có nội dung. Tiếp tục (KHÔNG overwrite file tồn tại)?"
        ):
            raise SystemExit(1)

    # 1. Create data dirs only (no tools/, no .venv/ — those are in global base)
    for d in ["raw/inbox", "raw", "wiki/.proposals", "rag/.rag_index"]:
        (wiki_dir / d).mkdir(parents=True, exist_ok=True)
        (wiki_dir / d / ".gitkeep").touch()
    (wiki_dir / "wiki").mkdir(exist_ok=True)

    # 2. Skeleton top-level
    if not (wiki_dir / "wiki/index.md").exists():
        (wiki_dir / "wiki/index.md").write_text(
            read_template("templates", "project", "wiki-index.md"),
            encoding="utf-8",
        )
        console.print("  [green]✓[/green] wiki/index.md")
    if not (wiki_dir / "wiki/log.md").exists():
        (wiki_dir / "wiki/log.md").write_text(
            read_template("templates", "project", "wiki-log.md"),
            encoding="utf-8",
        )
        console.print("  [green]✓[/green] wiki/log.md")

    # 3. Agent config files (_schema.md, AGENTS.md, CLAUDE.md)
    copied = _copy_agent_configs(wiki_dir)
    if copied:
        console.print(f"  [green]✓[/green] agent configs: {', '.join(copied)}")

    # 4. .gitignore (wiki-specific, copy from template if missing)
    if template_exists("templates", "wiki-gitignore") and not (wiki_dir / ".gitignore").exists():
        (wiki_dir / ".gitignore").write_text(
            read_template("templates", "wiki-gitignore"), encoding="utf-8"
        )
        console.print("  [green]✓[/green] .gitignore")

    # 5. .env point to global base
    if not (wiki_dir / ".env").exists():
        env_content = (
            f"# Point to global llm-wiki-base runtime.\n"
            f"# LLM_WIKI_BASE_DIR={base_dir}\n"
        )
        (wiki_dir / ".env").write_text(env_content, encoding="utf-8")
        console.print("  [green]✓[/green] .env (pointing to global base)")

    # 6. Install MCP config (per client) — global user config
    abs_wiki = wiki_dir.resolve()
    py_bin = get_base_python()
    server_cmd = [str(py_bin), str(base_dir / "tools" / "mcp_server.py")]
    server_env = {
        "WIKI_ROOT": str(abs_wiki),
        "WIKI_EMBED_MODEL": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "WIKI_BM25_WEIGHT": "0.5",
        "WIKI_VEC_WEIGHT": "0.5",
        "WIKI_MCP_NAME": server_name,
    }

    console.print()
    console.print("[bold]Install MCP config:[/bold]")
    for client in clients:
        try:
            cfg_path = install_mcp_config(client, server_name, server_cmd, server_env, cwd=str(abs_wiki))
            console.print(f"  [green]✓[/green] {client}: {cfg_path}")
        except Exception as e:
            console.print(f"  [red]✗[/red] {client}: {e}")

    # 7. Install skills per-wiki (auto)
    if skills_target != "skip":
        installed = install_skills(wiki_dir, target=skills_target, base_skills_dir="project")
        if installed:
            console.print(f"  [green]✓[/green] .agents/skills/: {', '.join(installed)}")
        else:
            console.print("  [yellow]![/yellow] skills source not found")

    # 8. Done
    console.print()
    console.print("[bold green]✓ Project wiki ready.[/bold green]")
    console.print()
    console.print(f"  Data:        {wiki_dir}/")
    console.print(f"  Base runtime: {base_dir}/ (global, shared)")
    console.print(f"  MCP config:  installed globally for {', '.join(clients)}")
    if skills_target != "skip":
        console.print(f"  Skills:      copied to {wiki_dir}/.agents/skills/ (per-wiki, scope = this wiki)")
    console.print()
    console.print("Next steps:")
    console.print(f"  1. Reload your AI client (Claude Code / OpenCode / Zed) to pick up MCP server")
    console.print(f"  2. From inside {wiki_dir}, use slash command /wiki-project-research <query>")
    console.print(f"  3. Or use MCP tool wiki_search directly")
    console.print(f"  4. (Optional) Edit MCP config — server name '{server_name}' → adjust if conflict")
    console.print(f"  5. Run from inside {wiki_dir}: [cyan]llm-wiki ingest raw/inbox/<file>[/cyan]")
