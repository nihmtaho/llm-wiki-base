"""Tests for global/user-level skill installation.

Global skills live in `~/.agents/skills/` (Command Code) and `~/.claude/skills/`
(Claude Code) — they are NOT per-wiki. They ship from `skills/global/` in package
data and are copied verbatim (idempotent) into the user's home skill directories.
"""
from pathlib import Path

from llm_wiki_base import _skills
from llm_wiki_base.cli import app


def test_available_global_skills_lists_shipped():
    """The contribute skill is discoverable in package data."""
    names = _skills.available_global_skills()
    assert "llm-wiki-base-contribute" in names


def test_install_contribute_skill_writes_to_both_global_dirs(tmp_path, monkeypatch):
    """install_global_skills copies SKILL.md to ~/.agents/skills/ + ~/.claude/skills/."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    installed = _skills.install_global_skills(["llm-wiki-base-contribute"])
    assert len(installed) == 2

    for dst in installed:
        skill_md = Path(dst) / "SKILL.md"
        assert skill_md.is_file()
        content = skill_md.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "name: llm-wiki-base-contribute" in content

    # Both global directories exist with the skill
    assert (home / ".agents" / "skills" / "llm-wiki-base-contribute" / "SKILL.md").is_file()
    assert (home / ".claude" / "skills" / "llm-wiki-base-contribute" / "SKILL.md").is_file()


def test_install_global_skills_idempotent(tmp_path, monkeypatch):
    """Re-running install overwrites with the same content."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    _skills.install_global_skills(["llm-wiki-base-contribute"])
    first = (home / ".agents" / "skills" / "llm-wiki-base-contribute" / "SKILL.md").read_text(encoding="utf-8")

    _skills.install_global_skills(["llm-wiki-base-contribute"])
    second = (home / ".agents" / "skills" / "llm-wiki-base-contribute" / "SKILL.md").read_text(encoding="utf-8")

    assert first == second  # same content


def test_install_unknown_global_skill_is_noop(tmp_path, monkeypatch):
    """Installing a non-existent skill returns empty list, no crash."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    installed = _skills.install_global_skills(["nonexistent-skill"])
    assert installed == []


def test_setup_personal_contribute_flag(runner, isolated_env, machine, tmp_path, monkeypatch):
    """`setup personal --contribute` installs the global skill to user dirs."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    machine("claude")

    result = runner.invoke(app, ["setup", "personal", "--name", "demo",
                                  "--yes", "--no-mcp", "--no-skills", "--contribute"])
    assert result.exit_code == 0, result.output

    home = isolated_env["home"]
    assert (home / ".agents" / "skills" / "llm-wiki-base-contribute" / "SKILL.md").is_file()
    assert (home / ".claude" / "skills" / "llm-wiki-base-contribute" / "SKILL.md").is_file()


def test_setup_personal_no_contribute_skips_install(runner, isolated_env, machine, tmp_path, monkeypatch):
    """`setup personal --no-contribute` does NOT install the global skill."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    machine("claude")

    result = runner.invoke(app, ["setup", "personal", "--name", "demo",
                                  "--yes", "--no-mcp", "--no-skills", "--no-contribute"])
    assert result.exit_code == 0, result.output

    home = isolated_env["home"]
    assert not (home / ".agents" / "skills" / "llm-wiki-base-contribute").exists()
    assert not (home / ".claude" / "skills" / "llm-wiki-base-contribute").exists()
