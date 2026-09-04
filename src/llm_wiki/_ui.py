"""Shared Rich presentation for the llm-wiki CLI.

Single home for glyphs, colors and layout (banners, panels, tables, rules)
so every command looks like one tool. Message *texts* stay at the call sites —
this module only decides how they look.
"""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def banner(title: str, body: str = "") -> None:
    """Cyan panel header for the wizard and init flows."""
    console.print(Panel(
        body,
        title=f"[bold cyan]{title}[/bold cyan]",
        border_style="cyan",
        padding=(0, 2),
    ))


def section(title: str) -> None:
    """Bold rule divider between output sections."""
    console.print()
    console.rule(f"[bold]{title}[/bold]")


def done_panel(title: str, rows: list[str], ok_style: bool = True) -> None:
    """Result summary panel — green ✓ by default, red ✗ for failures."""
    style = "green" if ok_style else "red"
    mark = "✓" if ok_style else "✗"
    console.print(Panel(
        "\n".join(rows),
        title=f"[bold {style}]{mark} {title}[/bold {style}]",
        border_style=style,
        padding=(0, 2),
    ))


def wiki_table(wikis: list[dict]) -> None:
    """Registry listing as a table: Name | Type | ID | Path | Added."""
    table = Table(
        title=f"{len(wikis)} wiki(s) in registry",
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Type", style="dim")
    table.add_column("ID", style="dim", overflow="fold")
    table.add_column("Path", overflow="fold")
    table.add_column("Added", style="dim", no_wrap=True)
    for w in wikis:
        tag = "project" if w.get("type") == "project" else "personal"
        table.add_row(
            w["name"],
            tag,
            w.get("id") or "—",
            w["path"],
            (w.get("added") or "—")[:10],
        )
    console.print(table)


def config_table(rows: list[tuple]) -> None:
    """Effective config as a table: Setting | Value | Source.

    Rows are ("section", name) or ("row", path, value_repr, source_label,
    source_style).
    """
    table = Table(header_style="bold cyan", show_lines=False, padding=(0, 2))
    table.add_column("Setting", overflow="fold")
    table.add_column("Value", overflow="fold")
    table.add_column("Source", no_wrap=True)
    for row in rows:
        if row[0] == "section":
            table.add_row(f"[bold]{row[1]}[/bold]", "", "")
        else:
            _, path, value, label, style = row
            table.add_row(path, value, f"[{style}]{label}[/{style}]")
    console.print(table)


def skill_table(items: list[tuple[str, str, str]]) -> None:
    """What-needs-an-AI-tool list as a table: Task | Skill | Note."""
    table = Table(header_style="bold cyan", show_lines=False, padding=(0, 1))
    table.add_column("Task", overflow="fold")
    table.add_column("Skill", style="cyan", no_wrap=True)
    table.add_column("Note", style="dim", overflow="fold")
    for what, skill, why in items:
        table.add_row(what, skill, why)
    console.print(table)


_state = {"quiet": False, "no_color": False, "debug": False}


def set_quiet(value: bool) -> None:
    _state["quiet"] = value


def set_no_color(value: bool) -> None:
    _state["no_color"] = value
    console.no_color = value


def set_debug(value: bool) -> None:
    _state["debug"] = value


def is_quiet() -> bool:
    return _state["quiet"]


def is_debug() -> bool:
    return _state["debug"]


def ok_panel(title: str, facts: list[str], next_steps: list[str] | None = None) -> None:
    """Success panel. Quiet mode prints facts only, no panel, no next steps."""
    if _state["quiet"]:
        for line in facts:
            console.print(line)
        return
    body = "\n".join(facts)
    if next_steps:
        numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(next_steps))
        body += f"\n[dim]Next:[/dim]\n{numbered}"
    console.print(Panel(
        body,
        title=f"[bold green]✓ {title}[/bold green]",
        border_style="green",
        padding=(0, 2),
    ))


def err_panel(what: str, fix: str = "") -> None:
    """Error panel. Quiet mode prints `Error: <what>` plus fix on one line each."""
    if _state["quiet"]:
        console.print(f"Error: {what}")
        if fix:
            console.print(f"Fix: {fix}")
        return
    body = what
    if fix:
        body += f"\n[dim]Fix:[/dim] {fix}"
    console.print(Panel(
        body,
        title="[bold red]✗ Error[/bold red]",
        border_style="red",
        padding=(0, 2),
    ))


def table(title: str, headers: list[str], rows: list[list[str]]) -> None:
    """Generic listing table. Quiet mode prints one ` | `-joined line per row."""
    if _state["quiet"]:
        for row in rows:
            console.print(" | ".join(row))
        return
    t = Table(title=title or None, header_style="bold cyan", show_lines=False)
    for h in headers:
        t.add_column(h, overflow="fold")
    for row in rows:
        t.add_row(*row)
    console.print(t)
