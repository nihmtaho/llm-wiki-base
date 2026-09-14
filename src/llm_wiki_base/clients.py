"""Which AI clients are actually installed on this machine.

`setup` must not offer to write a client's config file on faith: creating
`~/.codex/config.toml` on a machine without Codex leaves a file nothing reads
(and, for a project wiki, commits it into the team's repo). So the wizard asks
this module first and pre-checks only what it can prove.

Three kinds of evidence, any ONE of which counts as installed:

  1. a binary on PATH            (`shutil.which("claude")`)
  2. a user-scope config dir/file (`~/.config/opencode`, `~/.claude.json`, …)
  3. a macOS app bundle          (`/Applications/Zed.app`)

Nothing is assumed from defaults: when a client fails all three it stays in the
menu (the human may still know better than the probe) but starts unchecked and
says which probes it failed. See `_ui.err_panel`-adjacent rule in the project
taste: a silently-skipped component is a bug, so every "not detected" carries
its reason.

All paths expand HOME at call time — `config.CLIENT_PATHS` deliberately stores
strings for the same reason (see its module docstring).
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from llm_wiki_base.config import (
    CLIENT_PATHS,
    get_mcp_config_path,
    supports_project_scope,
)

#: How many probe locations to name in a "not detected" reason before truncating.
_MAX_PROBES_SHOWN = 2

#: Where macOS app bundles live. A module constant (not a literal) so a test can
#: point it at an empty dir — otherwise "clean machine" fixtures still see the
#: real /Applications and report clients that the fake HOME says are absent.
APPS_ROOT = Path("/Applications")


@dataclass(frozen=True)
class ClientState:
    """One row of the client menu: what it is, whether we saw it, and why."""

    key: str                      # canonical id — exactly what `-c` takes
    label: str                    # display name, e.g. "Claude Code"
    detected: bool
    evidence: str                 # "binary ~/.local/bin/claude" / "not detected (…)"
    target: str                   # file it would write, for the human to read
    scope: str                    # "project" | "global"

    @property
    def writes(self) -> str:
        """Where the entry lands — 'global' must always be spelled out to the user."""
        return f"{self.scope}: {self.target}"


def _expand(raw: str, home: Path) -> Path:
    """`~/.claude` → home-relative Path, without touching the real HOME env."""
    if raw == "~":
        return home
    if raw.startswith("~/"):
        return home / raw[2:]
    return Path(raw).expanduser()


def _display(path: Path, home: Path) -> str:
    """Shorten a path for a menu line: /Users/me/.claude → ~/.claude."""
    try:
        return "~/" + path.relative_to(home).as_posix()
    except ValueError:
        return str(path)


def _probes(client: str) -> tuple[list[str], list[str], list[str]]:
    spec = CLIENT_PATHS[client].get("detect") or {}
    return (list(spec.get("binaries") or []),
            list(spec.get("paths") or []),
            list(spec.get("apps") or []))


def _target(client: str, home: Path) -> tuple[str, str]:
    """(scope, file-to-write) as a human-readable string."""
    spec = CLIENT_PATHS[client]
    if supports_project_scope(client):
        return "project", str(spec["project_mcp"])
    try:
        return "global", _display(get_mcp_config_path(client), home)
    except (ValueError, KeyError):        # client with no config file at all
        return "global", "(no config file)"


def probe(client: str, home: Path | None = None) -> ClientState:
    """Ask the filesystem about one client. Never writes anything."""
    home = home or Path.home()
    binaries, paths, apps = _probes(client)
    scope, target = _target(client, home)
    label = CLIENT_PATHS[client].get("label") or client

    for binary in binaries:
        found = shutil.which(binary)
        if found:
            return ClientState(client, label, True,
                               f"binary {_display(Path(found), home)}", target, scope)
    for raw in paths:
        candidate = _expand(raw, home)
        if candidate.exists():
            return ClientState(client, label, True,
                               f"config {_display(candidate, home)}", target, scope)
    if sys.platform == "darwin":
        for app in apps:
            bundle = APPS_ROOT / f"{app}.app"
            if bundle.exists():
                return ClientState(client, label, True, str(bundle), target, scope)

    tried = [f"'{b}'" for b in binaries[:_MAX_PROBES_SHOWN]] + \
            [f"{p}" for p in paths[:_MAX_PROBES_SHOWN]]
    return ClientState(client, label, False,
                       f"not detected ({', '.join(tried) or 'no probes'})",
                       target, scope)


def detect(home: Path | None = None) -> list[ClientState]:
    """Every supported client, in menu order, with its evidence."""
    return [probe(client, home) for client in CLIENT_PATHS]


def detected_keys(states: list[ClientState] | None = None) -> list[str]:
    """Keys to pre-check in the wizard — empty when the machine has none."""
    return [s.key for s in (states if states is not None else detect()) if s.detected]


def choices(states: list[ClientState]) -> list[tuple[str, str]]:
    """(value, label) pairs for `_prompt.checkbox` — value is what `-c` takes."""
    out = []
    for s in states:
        suffix = "" if s.scope == "project" else f" → {s.writes}"
        mark = "✓" if s.detected else "?"
        out.append((s.key, f"[{mark}] {s.label:<14} {s.evidence}{suffix}"))
    return out


def as_rows(states: list[ClientState]) -> list[list[str]]:
    """Table rows for `setup doctor`: Client | Installed | Evidence | Writes."""
    return [[s.label, "yes" if s.detected else "no", s.evidence, s.writes]
            for s in states]


def client_flags(keys: list[str]) -> str:
    """The copy-pasteable `-c` tail a human can reuse non-interactively."""
    return " ".join(f"-c {k}" for k in keys)
