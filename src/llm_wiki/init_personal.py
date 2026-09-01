"""Init flow cho personal knowledge wiki — data only.

Sau refactor: runtime code (tools/, rag/, scripts/, .venv/) ở global `~/.llm-wiki-base/`.
Init chỉ tạo data folders + skeleton top-level + đăng ký wiki vào registry.toml +
cài centralized MCP config (mặc định, có thể --no-mcp để bỏ qua).

Usage:
    llm-wiki init personal [--name <wiki-name>] [--client claude] [--no-mcp] [--no-skills]

Cwd = wiki dir. Tạo raw/, wiki/, rag/.rag_index/ + skeleton + .agents/skills/ (auto).
"""
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

from llm_wiki._package_data import read_template, template_exists
from llm_wiki._skills import install_skills
from llm_wiki.base import get_base_dir
from llm_wiki.config import supported_clients
from llm_wiki.installer import install_centralized_mcp, CENTRALIZED_SERVER_NAME
from llm_wiki.registry import add_wiki

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
    cwd: Path,
    name: str | None,
    force: bool = False,
    skills_target: str = "universal",
    clients: list[str] | None = None,
    skip_mcp: bool = False,
) -> None:
    wiki_name = name or cwd.name
    base_dir = get_base_dir()

    if not base_dir.exists():
        console.print(f"[red]Error:[/red] Global base chưa cài: {base_dir}")
        console.print(f"  Chạy trước: [cyan]llm-wiki base install[/cyan]")
        raise SystemExit(1)

    console.print(f"[bold]Init personal wiki:[/bold] {wiki_name}")
    console.print(f"  at [cyan]{cwd}[/cyan]")
    console.print(f"  base: [cyan]{base_dir}[/cyan] (global runtime)")
    console.print(f"  MCP:  centralized server [cyan]{CENTRALIZED_SERVER_NAME}[/cyan]")

    # 1. Check empty
    if any(cwd.iterdir()) and not force:
        if not Confirm.ask(f"{cwd} đã có file/dir. Tiếp tục (KHÔNG overwrite)?"):
            raise SystemExit(1)

    # 2. Create data dirs only
    for d in ["raw/inbox", "raw", "wiki/.proposals", "rag/.rag_index"]:
        (cwd / d).mkdir(parents=True, exist_ok=True)
        (cwd / d / ".gitkeep").touch()
    (cwd / "wiki").mkdir(exist_ok=True)

    # 3. Skeleton top-level wiki/
    if not (cwd / "wiki/index.md").exists():
        (cwd / "wiki/index.md").write_text(
            read_template("templates", "personal", "wiki-index.md")
            .replace("{{wiki_name}}", wiki_name),
            encoding="utf-8",
        )
        console.print("  [green]✓[/green] wiki/index.md")
    if not (cwd / "wiki/log.md").exists():
        (cwd / "wiki/log.md").write_text(
            read_template("templates", "personal", "wiki-log.md"),
            encoding="utf-8",
        )
        console.print("  [green]✓[/green] wiki/log.md")

    # 4. Agent config files (_schema.md, AGENTS.md, CLAUDE.md)
    copied = _copy_agent_configs(cwd)
    if copied:
        console.print(f"  [green]✓[/green] agent configs: {', '.join(copied)}")

    # 5. .gitignore (wiki-specific, copy from template if missing)
    if template_exists("templates", "wiki-gitignore") and not (cwd / ".gitignore").exists():
        (cwd / ".gitignore").write_text(
            read_template("templates", "wiki-gitignore"), encoding="utf-8"
        )
        console.print("  [green]✓[/green] .gitignore")

    # 6. .env point to base dir (optional, for explicit override)
    if not (cwd / ".env").exists():
        env_content = (
            f"# Point to global llm-wiki-base runtime. Uncomment to override.\n"
            f"# LLM_WIKI_BASE_DIR={base_dir}\n\n"
            f"# Centralized MCP: server reads registry.toml từ base dir.\n"
            f"# AI tool chỉ định wiki qua param `wiki=<name>` khi gọi MCP tools.\n\n"
            f"# Embedding model + hybrid search weights (default OK)\n"
            f"# WIKI_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2\n"
            f"# WIKI_BM25_WEIGHT=0.5\n"
            f"# WIKI_VEC_WEIGHT=0.5\n"
        )
        (cwd / ".env").write_text(env_content, encoding="utf-8")
        console.print("  [green]✓[/green] .env (pointing to global base + MCP registry)")

    # 7. Registry — đăng ký wiki vào TOML (centralized MCP dùng để tìm wiki)
    add_wiki(wiki_name, str(cwd), wiki_type="personal")
    console.print(f"  [green]✓[/green] registry: '{wiki_name}' → {cwd}")

    # 8. Install centralized MCP config (default — not optional)
    if not skip_mcp:
        cli_clients = clients or ["claude"]
        console.print()
        console.print("[bold]Install centralized MCP config:[/bold]")
        for client in cli_clients:
            if client not in supported_clients():
                console.print(f"  [red]✗[/red] unknown client '{client}'. Supported: {supported_clients()}")
                continue
            try:
                cfg_path = install_centralized_mcp(client)
                console.print(f"  [green]✓[/green] {client}: {cfg_path}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {client}: {e}")
    else:
        console.print("  [yellow]![/yellow] MCP init skipped (--no-mcp)")

    # 9. Install skills per-wiki
    if skills_target != "skip":
        installed = install_skills(cwd, target=skills_target, base_skills_dir="personal")
        if installed:
            console.print(f"  [green]✓[/green] .agents/skills/: {', '.join(installed)}")
        else:
            console.print("  [yellow]![/yellow] skills source not found")

    # 10. Done
    console.print()
    console.print("[bold green]✓ Personal wiki ready.[/bold green]")
    console.print()
    console.print(f"  Data:        {cwd}/")
    console.print(f"  Base runtime: {base_dir}/ (global, shared)")
    console.print(f"  Registry:    '{wiki_name}' in centralized MCP registry")
    if not skip_mcp:
        console.print(f"  MCP:         {CENTRALIZED_SERVER_NAME} — installed in client config")
    if skills_target != "skip":
        console.print(f"  Skills:      copied to {cwd}/.agents/skills/ (per-wiki, scope = personal)")
    console.print()
    console.print("Next steps:")
    console.print(f"  1. Drop sources vào: {cwd}/raw/inbox/")
    console.print(f"  2. Chạy từ trong wiki dir: [cyan]llm-wiki ingest raw/inbox/<file>[/cyan]")
    console.print(f"  3. AI tool sẽ load skills + MCP tools từ: [cyan]{cwd}/.agents/skills/[/cyan]")
    console.print(f"  4. MCP search: wiki_search(query, wiki='{wiki_name}') hoặc để trống để search all")
    if not skip_mcp:
        console.print(f"  5. Reload AI client để pick up MCP server")
