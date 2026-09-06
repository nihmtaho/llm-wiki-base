"""Root research block injected by `llm-wiki init project`.

Covers template + `_ensure_root_research_block` + `run()` hook.
Idempotent: create → append → refresh-in-place, never duplicate.
"""


from llm_wiki import init_project
from llm_wiki._package_data import template_exists

START = "<!-- LLM_WIKI_RESEARCH_START -->"
END = "<!-- LLM_WIKI_RESEARCH_END -->"


def test_template_shipped():
    assert template_exists("templates", "agents", "research-block.md")


def test_creates_both_files_with_markers(tmp_path):
    touched = init_project._ensure_root_research_block(tmp_path)
    assert touched == ["AGENTS.md", ".claude/CLAUDE.md"]
    for rel in touched:
        text = (tmp_path / rel).read_text(encoding="utf-8")
        assert text.count(START) == 1
        assert text.count(END) == 1


def test_idempotent_rerun_single_block(tmp_path):
    init_project._ensure_root_research_block(tmp_path)
    init_project._ensure_root_research_block(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count(START) == 1
    assert text.count(END) == 1


def test_preserves_existing_content(tmp_path):
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# My project\n", encoding="utf-8")
    init_project._ensure_root_research_block(tmp_path)
    text = agents.read_text(encoding="utf-8")
    assert text.startswith("# My project\n")
    assert text.count(START) == 1


def test_refreshes_stale_block(tmp_path):
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        f"# P\n\n{START}\nOLD SENTINEL\n{END}\n", encoding="utf-8"
    )
    init_project._ensure_root_research_block(tmp_path)
    text = agents.read_text(encoding="utf-8")
    assert "OLD SENTINEL" not in text
    assert text.startswith("# P\n")
    assert text.count(START) == 1
    assert text.count(END) == 1


def test_run_hooks_root_block(tmp_path, isolated_env, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "proj"
    root.mkdir()
    kwargs = dict(
        root=root,
        wiki_subdir="project-wiki",
        clients=[],
        skills_target="skip",
        skip_mcp=True,
        register=False,
        force=True,
    )
    init_project.run(**kwargs)
    init_project.run(**kwargs)  # re-run must not duplicate
    for rel in ("AGENTS.md", ".claude/CLAUDE.md"):
        text = (root / rel).read_text(encoding="utf-8")
        assert text.count(START) == 1, rel
        assert text.count(END) == 1, rel
    # wiki-scoped configs still land inside the wiki dir, not root
    assert (root / "project-wiki" / "AGENTS.md").exists()
