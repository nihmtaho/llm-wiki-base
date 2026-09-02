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
from llm_wiki.config_file import ensure_wiki_identity
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
    mcp_scope: str = "user",
    lang: str | None = None,
    register: bool = True,
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

    # 5b. .llm-wiki.toml (behavior config — commit vào wiki repo)
    if template_exists("templates", "llm-wiki.toml") and not (cwd / ".llm-wiki.toml").exists():
        (cwd / ".llm-wiki.toml").write_text(
            read_template("templates", "llm-wiki.toml"), encoding="utf-8"
        )
        console.print("  [green]✓[/green] .llm-wiki.toml (wiki config — commit file này)")
    # `[wiki].profile` phải đúng loại wiki — skill đọc nó để chọn chế độ.
    # Chạy cả khi file đã tồn tại (re-init wiki cũ chưa có section này).
    if ensure_wiki_identity(cwd / ".llm-wiki.toml", profile="personal", lang=lang):
        console.print("  [green]✓[/green] .llm-wiki.toml: \\[wiki\\].profile = personal"
                      + (f", lang = {lang}" if lang else ""))

    # 5c. eval/golden.toml — bộ query vàng cho `llm-wiki eval` (commit vào wiki repo)
    if template_exists("templates", "eval-golden.toml"):
        golden = cwd / "eval" / "golden.toml"
        if not golden.exists():
            golden.parent.mkdir(parents=True, exist_ok=True)
            golden.write_text(
                read_template("templates", "eval-golden.toml"), encoding="utf-8"
            )
            console.print("  [green]✓[/green] eval/golden.toml (query vàng — thay bằng query thật)")
        else:
            console.print("  [dim]eval/golden.toml đã tồn tại — giữ nguyên[/dim]")

    # 6. .env point to base dir (optional, for explicit override)
    if not (cwd / ".env").exists():
        env_content = (
            f"# Point to global llm-wiki-base runtime. Uncomment to override.\n"
            f"# LLM_WIKI_BASE_DIR={base_dir}\n\n"
            f"# Centralized MCP: server reads registry.toml từ base dir.\n"
            f"# AI tool chỉ định wiki qua param `wiki=<name>` khi gọi MCP tools.\n"
        )
        (cwd / ".env").write_text(env_content, encoding="utf-8")
        console.print("  [green]✓[/green] .env (pointing to global base + MCP registry)")

    # 7. Registry — đăng ký wiki vào TOML (centralized MCP dùng để tìm wiki)
    if register:
        wiki_name = add_wiki(wiki_name, str(cwd), wiki_type="personal")
        console.print(f"  [green]✓[/green] registry: '{wiki_name}' → {cwd}")
    else:
        console.print("  [dim]registry: BỎ QUA (--no-register) — AI tool sẽ không thấy "
                      "wiki này qua `wiki=`[/dim]")

    # 8. Install centralized MCP config (default — not optional)
    mcp_results: list = []
    mcp_failed: list[tuple[str, str]] = []
    if not skip_mcp:
        cli_clients = clients or ["claude"]
        console.print()
        console.print("[bold]Install centralized MCP config:[/bold]")
        for client in cli_clients:
            if client not in supported_clients():
                console.print(f"  [red]✗[/red] unknown client '{client}'. "
                              f"Hỗ trợ: {', '.join(supported_clients())}")
                mcp_failed.append((client, "client không được hỗ trợ"))
                continue
            try:
                res = install_centralized_mcp(client, scope=mcp_scope,
                                              project_root=cwd if mcp_scope == "project" else None)
                mcp_results.append(res)
                console.print(f"  [green]✓[/green] {res.describe()}")
            except Exception as e:
                mcp_failed.append((client, str(e)))
                console.print(f"  [red]✗[/red] {client}: {e}")
    else:
        console.print("  [yellow]![/yellow] MCP init skipped (--no-mcp) — "
                      "AI tool sẽ KHÔNG thấy wiki này qua `wiki=`")

    # 9. Install skills. Personal wiki = 1 folder duy nhất nên wiki scope và
    #    codebase scope trùng nhau → cài "all" vào cwd.
    installed: list[str] = []
    if skills_target != "skip":
        installed = install_skills(cwd, target=skills_target, subset="all",
                                   clients=clients or [])
        if installed:
            console.print(f"  [green]✓[/green] {cwd}/.agents/skills/: {', '.join(installed)}")
        else:
            console.print("  [yellow]![/yellow] không cài được skill nào — kiểm tra package "
                          "data (`llm-wiki base install` lại sau khi nâng cấp)")

    # 10. Done
    console.print()
    console.print("[bold green]✓ Personal wiki ready.[/bold green]")
    console.print()
    console.print(f"  Data:        {cwd}/")
    console.print(f"  Base runtime: {base_dir}/ (global, shared)")
    console.print(f"  Registry:    '{wiki_name}' in centralized MCP registry")
    for res in mcp_results:
        console.print(f"  MCP {res.client:<11} {res.describe()}")
    if skip_mcp:
        console.print("  MCP:         [dim]bỏ qua[/dim]")
    elif mcp_failed:
        console.print(f"  MCP:         [red]LỖI với {', '.join(c for c, _ in mcp_failed)}[/red] "
                      "— sửa rồi chạy lại init này (nó idempotent, không phá dữ liệu)")
    if installed:
        console.print(f"  Skills:      {cwd}/.agents/skills/ (scope = wiki này + cross-wiki research)")
    console.print()
    console.print("Next steps:")
    console.print(f"  1. Drop sources vào: {cwd}/raw/inbox/")
    console.print(f"  2. Ingest thật sự = chạy skill [bold]llm-wiki-ingest[/bold] trong AI tool "
                  f"(CLI `llm-wiki ingest` chỉ index file đã có, không viết page)")
    console.print(f"  3. AI tool load skills từ [cyan]{cwd}/.agents/skills/[/cyan] — "
                  "Command Code đọc `.agents/skills/` trực tiếp; Claude/OpenCode đã được link")
    console.print(f"  4. MCP search: wiki_search(query, wiki='{wiki_name}'), hoặc wiki=\"\" để search mọi wiki")
    if not skip_mcp:
        console.print("  5. [bold]Khởi động lại AI tool[/bold] — MCP process cũ giữ registry trong memory")
