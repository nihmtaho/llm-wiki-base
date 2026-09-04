"""Init flow cho project wiki.

Usage:
    llm-wiki init project [--root <dir>] [--wiki-dir <name>] [--client claude] [--no-skills] [--no-mcp]

Tạo <root>/<wiki-dir>/ chứa data (wiki, raw, rag) + cài MCP entry vào file
per-project ở root repo (commit vào VCS được) + copy skills vào
<wiki_dir>/.agents/skills/.

Centralized MCP server (`llm-wiki-base-mcp`) đã được cài sẵn trong global base —
init chỉ cần ensure MCP config tồn tại ở client config và đăng ký wiki vào registry.toml.

Runtime code (tools/, rag/, scripts/, .venv/) ở global `~/.llm-wiki-base/`.
Project wiki chỉ chứa data + .env + .llm-wiki.toml + .agents/skills/.
"""
from pathlib import Path

import typer
from rich.prompt import Confirm

from llm_wiki._package_data import read_template, template_exists
from llm_wiki._skills import install_skills
from llm_wiki import _ui
from llm_wiki._ui import console
from llm_wiki.base import get_base_dir, get_base_python
from llm_wiki.config import supported_clients
from llm_wiki.config_file import ensure_wiki_identity
from llm_wiki.installer import install_centralized_mcp, CENTRALIZED_SERVER_NAME
from llm_wiki.registry import add_wiki


def _copy_agent_configs(cwd: Path) -> list[str]:
    """Copy agent config templates vào wiki: AGENTS.md (+ _schema.md) ở root,
    CLAUDE.md (chỉ tag @AGENTS.md) vào .claude/."""
    copied: list[str] = []
    for name in ("_schema.md", "AGENTS.md"):
        if not template_exists("templates", "agents", name):
            continue
        dst = cwd / name
        if dst.exists():
            continue
        dst.write_text(read_template("templates", "agents", name), encoding="utf-8")
        copied.append(name)
    if template_exists("templates", "agents", "CLAUDE.md"):
        dst = cwd / ".claude" / "CLAUDE.md"
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(read_template("templates", "agents", "CLAUDE.md"),
                           encoding="utf-8")
            copied.append(".claude/CLAUDE.md")
    return copied


RESEARCH_START = "<!-- LLM_WIKI_RESEARCH_START -->"
RESEARCH_END = "<!-- LLM_WIKI_RESEARCH_END -->"


def _upsert_marked_block(path: Path, block: str) -> bool:
    """Append or refresh a marked block in a root agent file. Idempotent."""
    start, end = RESEARCH_START, RESEARCH_END
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if start in text and end in text:
            pre, _, rest = text.partition(start)
            _, _, post = rest.partition(end)
            path.write_text(f"{pre}{block}{post}", encoding="utf-8")
            return True
        path.write_text(f"{text.rstrip()}\n\n{block}\n", encoding="utf-8")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{block}\n", encoding="utf-8")
    return True


def _ensure_root_research_block(root: Path) -> list[str]:
    """Ensure root AGENTS.md + .claude/CLAUDE.md point at research skill."""
    if not template_exists("templates", "agents", "research-block.md"):
        return []
    block = read_template("templates", "agents", "research-block.md").strip() + "\n"
    touched: list[str] = []
    for rel in ("AGENTS.md", ".claude/CLAUDE.md"):
        if _upsert_marked_block(root / rel, block):
            touched.append(rel)
    return touched


def run(
    root: Path,
    wiki_subdir: str,
    clients: list[str],
    server_name: str = CENTRALIZED_SERVER_NAME,
    force: bool = False,
    skills_target: str = "universal",
    skip_mcp: bool = False,
    lang: str | None = None,
    register: bool = True,
) -> None:
    wiki_dir = (root / wiki_subdir).resolve()
    base_dir = get_base_dir()

    if not base_dir.exists():
        _ui.err_panel(f"Global base chưa cài: {base_dir}", "llm-wiki setup tools")
        raise typer.Exit(1)

    wiki_name = wiki_subdir
    _ui.banner(f"Init project wiki: {wiki_name}",
               f"project root  : [cyan]{root}[/cyan]\n"
               f"wiki subdir   : [cyan]{wiki_dir}[/cyan]\n"
               f"base runtime  : [cyan]{base_dir}[/cyan]\n"
               f"clients       : {', '.join(clients) if clients else '(none)'}\n"
               f"MCP server    : {server_name}")

    # Validate clients
    for c in clients:
        if c not in supported_clients():
            _ui.err_panel(f"unknown client '{c}'. Supported: {supported_clients()}",
                          "llm-wiki setup --help")
            raise typer.Exit(1)

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

    # 3. Agent config files (AGENTS.md + _schema.md ở root, CLAUDE.md ở .claude/)
    copied = _copy_agent_configs(wiki_dir)
    if copied:
        console.print(f"  [green]✓[/green] agent configs: {', '.join(copied)}")

    # 4. .gitignore (wiki-specific, copy from template if missing)
    if template_exists("templates", "wiki-gitignore") and not (wiki_dir / ".gitignore").exists():
        (wiki_dir / ".gitignore").write_text(
            read_template("templates", "wiki-gitignore"), encoding="utf-8"
        )
        console.print("  [green]✓[/green] .gitignore")

    # 4b. .llm-wiki.toml (behavior config — commit vào wiki repo)
    if template_exists("templates", "llm-wiki.toml") and not (wiki_dir / ".llm-wiki.toml").exists():
        (wiki_dir / ".llm-wiki.toml").write_text(
            read_template("templates", "llm-wiki.toml"), encoding="utf-8"
        )
        console.print("  [green]✓[/green] .llm-wiki.toml (wiki config — commit file này)")
    # Project wiki PHẢI là profile codebase (template mặc định là personal).
    if ensure_wiki_identity(wiki_dir / ".llm-wiki.toml", profile="codebase", lang=lang):
        console.print("  [green]✓[/green] .llm-wiki.toml: \\[wiki].profile = codebase"
                      + (f", lang = {lang}" if lang else ""))

    # 4c. eval/golden.toml — bộ query vàng cho `llm-wiki eval` (commit vào wiki repo)
    if template_exists("templates", "eval-golden.toml"):
        golden = wiki_dir / "eval" / "golden.toml"
        if not golden.exists():
            golden.parent.mkdir(parents=True, exist_ok=True)
            golden.write_text(
                read_template("templates", "eval-golden.toml"), encoding="utf-8"
            )
            console.print("  [green]✓[/green] eval/golden.toml (query vàng — thay bằng query thật)")
        else:
            console.print("  [dim]eval/golden.toml đã tồn tại — giữ nguyên[/dim]")

    # 5. .env point to global base
    if not (wiki_dir / ".env").exists():
        env_content = (
            f"# Point to global llm-wiki-base runtime.\n"
            f"# LLM_WIKI_BASE_DIR={base_dir}\n\n"
            f"# Centralized MCP: server reads registry.toml từ base dir.\n"
            f"# AI tool chỉ định wiki qua param `wiki=<name>` khi gọi MCP tools.\n"
        )
        (wiki_dir / ".env").write_text(env_content, encoding="utf-8")
        console.print("  [green]✓[/green] .env (pointing to global base + MCP registry)")

    # 6. Registry — đăng ký wiki vào TOML (centralized MCP dùng để tìm wiki)
    if register:
        wiki_name = add_wiki(wiki_name, str(wiki_dir), wiki_type="project")
        console.print(f"  [green]✓[/green] registry: '{wiki_name}' → {wiki_dir}")
    else:
        console.print("  [dim]registry: BỎ QUA (--no-register) — AI tool sẽ không thấy "
                      "wiki này qua `wiki=`[/dim]")

    # 7. Install centralized MCP config vào per-project wiki
    #    (<root>/.mcp.json, opencode.jsonc, … — commit vào VCS cho cả team).
    mcp_results: list = []
    mcp_failed: list[tuple[str, str]] = []
    if not skip_mcp and clients:
        console.print()
        console.print("[bold]Cài MCP vào per-project wiki:[/bold]")
        for client in clients:
            try:
                res = install_centralized_mcp(
                    client, server_name=server_name,
                    scope="project", project_root=root)
                mcp_results.append(res)
                console.print(f"  [green]✓[/green] {client}: {res.describe()}")
            except ValueError as e:
                # Client chưa có file MCP project-scope (vd zed) → bỏ qua, không lỗi.
                console.print(f"  [dim]–[/dim] {client}: {e}")
            except Exception as e:
                mcp_failed.append((client, str(e)))
                console.print(f"  [red]✗[/red] {client}: {e}")

    # 8. Install skills — 2 scope khác nhau, xem docstring `_skills`.
    #    `wiki`     → <wiki_dir>/.agents/skills/   (vận hành chính wiki này)
    #    `codebase` → <root>/.agents/skills/       (research xuyên wiki, cần thấy
    #                                                mọi wiki nên KHÔNG đặt trong wiki)
    installed_wiki: list[str] = []
    installed_root: list[str] = []
    if skills_target != "skip":
        installed_wiki = install_skills(wiki_dir, target=skills_target, subset="wiki",
                                        clients=clients)
        installed_root = install_skills(root, target=skills_target, subset="codebase",
                                        clients=clients)
        if installed_wiki:
            console.print(f"  [green]✓[/green] {wiki_dir}/.agents/skills/: "
                          f"{', '.join(installed_wiki)}")
        if installed_root:
            console.print(f"  [green]✓[/green] {root}/.agents/skills/: "
                          f"{', '.join(installed_root)}  [dim](scope = cả codebase)[/dim]")
        if not installed_wiki and not installed_root:
            console.print("  [yellow]![/yellow] không cài được skill nào — kiểm tra "
                          "package data (`llm-wiki base install` lại sau khi nâng cấp)")

    # 8b. Root research pointers (AGENTS.md + .claude/CLAUDE.md ở repo root)
    research_touched = _ensure_root_research_block(root.resolve())
    if research_touched:
        console.print(f"  [green]✓[/green] root research block: {', '.join(research_touched)}")

    # 9. Done
    rows = [
        f"Data:         {wiki_dir}/",
        f"Base runtime: {base_dir}/ (global, shared)",
        f"Registry:     {server_name} server → registry.toml trong base dir",
    ]
    if research_touched:
        rows.append(f"Research:     {', '.join(research_touched)} (root, idempotent)")
    for res in mcp_results:
        rows.append(f"MCP {res.client:<11} {res.describe()}")
    if skip_mcp:
        rows.append("MCP:          [dim]bỏ qua (--no-mcp)[/dim] — AI tool sẽ không thấy wiki")
    elif mcp_failed:
        rows.append(f"MCP:          [red]LỖI với {', '.join(c for c, _ in mcp_failed)}[/red] "
                    "— sửa rồi chạy lại lệnh init này (nó idempotent)")
    if installed_wiki:
        rows.append(f"Skills:       {wiki_dir}/.agents/skills/ (wiki scope)")
    if installed_root:
        rows.append(f"Skills:       {root}/.agents/skills/ (codebase scope)")
    _ui.done_panel("Project wiki ready", rows)
    console.print()
    console.print("Next steps:")
    console.print("  1. [bold]Khởi động lại AI tool[/bold] để MCP server nạp lại registry "
                  "(process cũ giữ registry trong memory)")
    console.print(f"  2. Research xuyên wiki từ repo này: /llm-wiki-research <câu hỏi> "
                  f"(skill ở {root}/.agents/skills/)")
    console.print(f"  3. Hoặc MCP tool: wiki_search(query, wiki='{wiki_name}') — "
                  "để wiki=\"\" để search mọi wiki")
    console.print(f"  4. Đăng ký wiki khác (nếu có): [cyan]llm-wiki wiki add <name> <path> --type project[/cyan]")
    console.print(f"  5. Nạp source đầu tiên: [cyan]cd {wiki_dir} && llm-wiki ingest raw/inbox/<file>[/cyan]"
                  " (CLI chỉ index; viết page là việc của skill llm-wiki-ingest trong AI tool)")
    console.print(f"  6. Đo retrieval sau khi có vài page: [cyan]llm-wiki eval --compare[/cyan]")
