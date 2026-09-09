"""`llm-wiki-base uninstall` — gỡ footprint của tool, GIỮ NGUYÊN dữ liệu wiki.

Ba lớp:
  1. installer: nhận diện + gỡ đúng entry của ta, giữ server khác, không phá file hỏng.
  2. _skills + init_project: gỡ skill của ta + link + block research.
  3. uninstall.build_plan/apply_plan + CLI: end-to-end, và data wiki còn nguyên.
"""
import json
from pathlib import Path

from llm_wiki_base import _skills, init_project, installer
from llm_wiki_base import uninstall as U
from llm_wiki_base.cli import app

# ─────────────────────────────────────────────────────────────────────────────
# installer: scan + remove MCP entries
# ─────────────────────────────────────────────────────────────────────────────


def _write_cfg(path: Path, servers: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8")
    return path


def test_is_our_entry_by_command_shape():
    ours = {"command": "llm-wiki-base", "args": ["serve", "--mcp"]}
    legacy = {"command": "/x/.llm-wiki-base/.venv/bin/python",
              "args": ["/x/.llm-wiki-base/tools/mcp_base_server.py"]}
    foreign = {"command": "npx", "args": ["-y", "@modelcontextprotocol/servers"]}
    assert installer.is_our_entry(ours)
    assert installer.is_our_entry(legacy)
    assert not installer.is_our_entry(foreign)
    assert not installer.is_our_entry("not a dict")  # type: ignore[arg-type]


def test_find_and_remove_keeps_other_servers(tmp_path):
    cfg = _write_cfg(tmp_path / ".mcp.json", {
        "llm-wiki-base-mcp": {"command": "llm-wiki-base", "args": ["serve", "--mcp"]},
        "keepme": {"command": "npx", "args": ["-y", "other"]},
    })
    assert installer.find_our_mcp_entries("claude", cfg) == ["llm-wiki-base-mcp"]
    removed, note = installer.remove_our_mcp_entries("claude", cfg)
    assert note == "removed" and removed == ["llm-wiki-base-mcp"]
    data = json.loads(cfg.read_text())
    assert "keepme" in data["mcpServers"]
    assert "llm-wiki-base-mcp" not in data["mcpServers"]


def test_remove_deletes_file_when_only_our_server(tmp_path):
    cfg = _write_cfg(tmp_path / ".mcp.json", {
        "llm-wiki-base-mcp": {"command": "llm-wiki-base", "args": ["serve", "--mcp"]},
    })
    _names, note = installer.remove_our_mcp_entries("claude", cfg)
    assert note == "removed"
    assert not cfg.exists()          # file trống hoàn toàn → xoá


def test_remove_custom_server_name_still_caught(tmp_path):
    cfg = _write_cfg(tmp_path / ".mcp.json", {
        "my-renamed": {"command": "llm-wiki-base", "args": ["serve", "--mcp"]},
    })
    removed, note = installer.remove_our_mcp_entries("claude", cfg)
    assert note == "removed" and removed == ["my-renamed"]


def test_unreadable_file_is_left_alone(tmp_path):
    cfg = tmp_path / ".mcp.json"
    cfg.write_text("{ this is not json ", encoding="utf-8")
    _names, note = installer.remove_our_mcp_entries("claude", cfg)
    assert note == "unreadable"
    assert cfg.read_text().startswith("{ this")   # không bị ghi đè


def test_no_entry_no_change(tmp_path):
    cfg = _write_cfg(tmp_path / ".mcp.json", {
        "someone-else": {"command": "uvx", "args": ["pkg"]},
    })
    _names, note = installer.remove_our_mcp_entries("claude", cfg)
    assert note == "no-entry"
    assert "someone-else" in json.loads(cfg.read_text())["mcpServers"]


# ─────────────────────────────────────────────────────────────────────────────
# _skills: uninstall our skills + client links
# ─────────────────────────────────────────────────────────────────────────────


def _make_skills(root: Path):
    """Layout thật sau `install_skills`: skill của ta + manifest KHAI đúng tên của ta,
    kèm một skill user tự viết (không có trong manifest) để chứng minh nó còn lại."""
    skills = root / ".agents" / "skills"
    (skills / "llm-wiki-base-ingest").mkdir(parents=True)
    (skills / "llm-wiki-base-ingest" / "SKILL.md").write_text("# ingest\n", encoding="utf-8")
    (skills / "user-custom-skill").mkdir()
    (skills / "user-custom-skill" / "SKILL.md").write_text("# mine\n", encoding="utf-8")
    (skills / _skills.MANIFEST).write_text(
        json.dumps({"skills": ["llm-wiki-base-ingest"], "version": 1}), encoding="utf-8")
    # claude dir link + opencode flat link trỏ vào skill của ta
    cs = root / ".claude" / "skills"
    cs.mkdir(parents=True)
    (cs / "llm-wiki-base-ingest").symlink_to(
        (skills / "llm-wiki-base-ingest").resolve(), target_is_directory=True)
    oc = root / ".opencode" / "commands"
    oc.mkdir(parents=True)
    (oc / "llm-wiki-base-ingest.md").symlink_to(
        (skills / "llm-wiki-base-ingest" / "SKILL.md").resolve())
    return skills


def test_uninstall_skills_removes_ours_keeps_user(tmp_path):
    skills = _make_skills(tmp_path)
    removed = _skills.uninstall_skills(tmp_path)
    assert "llm-wiki-base-ingest" in removed
    assert (skills / "user-custom-skill").is_dir()          # skill user giữ lại
    assert not (skills / "llm-wiki-base-ingest").exists()
    assert not (tmp_path / ".claude" / "skills" / "llm-wiki-base-ingest").exists()
    assert not (tmp_path / ".opencode" / "commands" / "llm-wiki-base-ingest.md").exists()
    assert not (skills / _skills.MANIFEST).exists()          # manifest bị dọn


def test_find_our_skills_read_only(tmp_path):
    _make_skills(tmp_path)
    names, links = _skills.find_our_skills(tmp_path)
    assert names == ["llm-wiki-base-ingest"]
    assert len(links) == 2
    # read-only: chưa xoá gì
    assert (tmp_path / ".agents" / "skills" / "llm-wiki-base-ingest").is_dir()


# ─────────────────────────────────────────────────────────────────────────────
# init_project: strip research block
# ─────────────────────────────────────────────────────────────────────────────


def test_strip_research_block_preserves_user_text(tmp_path):
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Keep me\n\ncontent\n", encoding="utf-8")
    init_project._ensure_root_research_block(tmp_path)
    assert init_project.has_research_block(agents)
    touched = init_project.strip_research_block(tmp_path)
    assert "AGENTS.md" in touched
    assert not init_project.has_research_block(agents)
    assert "# Keep me" in agents.read_text(encoding="utf-8")


def test_strip_research_block_removes_file_it_only_created(tmp_path):
    init_project._ensure_root_research_block(tmp_path)   # file chỉ có block của ta
    init_project.strip_research_block(tmp_path)
    assert not (tmp_path / "AGENTS.md").exists()


# ─────────────────────────────────────────────────────────────────────────────
# uninstall plan: end-to-end, data wiki còn nguyên
# ─────────────────────────────────────────────────────────────────────────────


def _full_personal_wiki(wiki: Path, base: Path):
    wiki.mkdir(parents=True)
    (wiki / "raw" / "inbox").mkdir(parents=True)
    (wiki / "raw" / "inbox" / "note.md").write_text("keep me", encoding="utf-8")
    (wiki / "wiki").mkdir()
    (wiki / "wiki" / "index.md").write_text("the wiki", encoding="utf-8")
    (wiki / "rag").mkdir()
    _make_skills(wiki)
    _write_cfg(wiki / ".mcp.json", {
        "llm-wiki-base-mcp": {"command": "llm-wiki-base", "args": ["serve", "--mcp"]},
    })
    (wiki / ".llm-wiki-base").mkdir()
    (wiki / ".llm-wiki-base" / "VERSION").write_text("v0.1.1", encoding="utf-8")


def test_build_plan_finds_footprint(isolated_env, monkeypatch):
    base = isolated_env["base"]
    (base / "tools").mkdir()
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(base / "registry.toml"))
    from llm_wiki_base import registry
    wiki = isolated_env["home"] / "notes"
    _full_personal_wiki(wiki, base)
    registry.add_wiki("notes", str(wiki), wiki_type="personal")

    plan = U.build_plan(include_user=False)
    assert plan.base_exists
    assert any(w.name == "notes" for w in plan.wikis)
    c = plan.counts()
    assert c["mcp_entries"] == 1
    assert c["skills"] >= 1
    assert c["state_dirs"] == 1


def test_apply_removes_footprint_keeps_data(isolated_env, monkeypatch):
    base = isolated_env["base"]
    (base / "tools").mkdir()
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(base / "registry.toml"))
    from llm_wiki_base import registry
    wiki = isolated_env["home"] / "notes"
    _full_personal_wiki(wiki, base)
    registry.add_wiki("notes", str(wiki), wiki_type="personal")

    plan = U.build_plan(include_user=False)
    summary = U.apply_plan(plan)

    # footprint biến mất
    assert not base.exists()
    assert not (wiki / ".mcp.json").exists()
    assert not (wiki / ".llm-wiki-base").exists()
    assert not (wiki / ".agents" / "skills" / "llm-wiki-base-ingest").exists()
    assert summary.base_dir_removed
    # DATA wiki còn nguyên
    assert (wiki / "raw" / "inbox" / "note.md").read_text() == "keep me"
    assert (wiki / "wiki" / "index.md").read_text() == "the wiki"
    assert (wiki / "rag").is_dir()


def test_keep_base_preserves_runtime(isolated_env, monkeypatch):
    base = isolated_env["base"]
    (base / "tools").mkdir()
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(base / "registry.toml"))
    from llm_wiki_base import registry
    wiki = isolated_env["home"] / "notes"
    _full_personal_wiki(wiki, base)
    registry.add_wiki("notes", str(wiki), wiki_type="personal")
    plan = U.build_plan(include_user=False)
    summary = U.apply_plan(plan, keep_base=True)
    assert base.exists() and not summary.base_dir_removed
    assert not (wiki / ".mcp.json").exists()      # vẫn dọn MCP entry


def test_extra_roots_clean_unregistered_wiki(isolated_env, monkeypatch):
    """Wiki tạo bằng --no-register không có trong registry → `--path` vẫn dọn được,
    và truyền trùng một wiki đã đăng ký không khiến footprint bị tính hai lần."""
    base = isolated_env["base"]
    (base / "tools").mkdir()
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(base / "registry.toml"))
    from llm_wiki_base import registry

    unregistered = isolated_env["home"] / "solo"
    _full_personal_wiki(unregistered, base)
    registered = isolated_env["home"] / "notes"
    _full_personal_wiki(registered, base)
    registry.add_wiki("notes", str(registered), wiki_type="personal")

    plan = U.build_plan(extra_roots=[unregistered, registered], include_user=False)
    names = sorted(w.name for w in plan.wikis)
    assert names == ["notes", "solo"]          # 'notes' chỉ xuất hiện một lần

    summary = U.apply_plan(plan)
    assert summary.mcp_entries >= 2               # cả hai wiki đều bị gỡ MCP
    assert not (unregistered / ".mcp.json").exists()
    assert (unregistered / "raw" / "inbox" / "note.md").exists()
    assert (registered / "wiki" / "index.md").exists()


def test_looks_like_base_dir_guard():
    assert U.looks_like_base_dir(Path.home() / ".llm-wiki-base")   # đúng tên mặc định
    assert not U.looks_like_base_dir(Path.home())                  # không xoá $HOME
    assert not U.looks_like_base_dir(Path("/"))                    # không xoá root


def test_apply_refuses_to_rmtree_non_runtime_base(isolated_env, monkeypatch):
    """`LLM_WIKI_BASE_DIR` trỏ vào folder không phải runtime → KHÔNG được xoá."""
    notreal = isolated_env["home"] / "important"
    notreal.mkdir()
    (notreal / "data.txt").write_text("precious", encoding="utf-8")
    monkeypatch.setenv("LLM_WIKI_BASE_DIR", str(notreal))
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(notreal / "registry.toml"))

    plan = U.build_plan(include_user=False)
    assert plan.base_exists                          # có tồn tại, nhưng…
    summary = U.apply_plan(plan)

    assert not summary.base_dir_removed              # …không bị xoá
    assert (notreal / "data.txt").read_text() == "precious"
    assert any("refusing to delete" in w for w in summary.warnings)


def test_project_wiki_shared_root(isolated_env, monkeypatch):
    """Project wiki: MCP + codebase skill + research block nằm ở REPO ROOT, không
    phải wiki subdir. Data wiki vẫn phải còn sau uninstall."""
    base = isolated_env["base"]
    (base / "tools").mkdir()
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(base / "registry.toml"))
    from llm_wiki_base import registry

    repo = isolated_env["home"] / "repo"
    wiki = repo / "project-wiki"
    wiki.mkdir(parents=True)
    (wiki / "wiki").mkdir()
    (wiki / "wiki" / "page.md").write_text("knowledge", encoding="utf-8")
    # codebase skill + MCP + block research đều ở repo root
    _make_skills(repo)
    _write_cfg(repo / ".mcp.json", {
        "llm-wiki-base-mcp": {"command": "llm-wiki-base", "args": ["serve", "--mcp"]},
    })
    init_project._ensure_root_research_block(repo)
    registry.add_wiki("repo-wiki", str(wiki), wiki_type="project")

    plan = U.build_plan(include_user=False)
    c = plan.counts()
    assert c["shared_targets"] == 1
    assert c["mcp_entries"] == 1
    assert c["research"] >= 1

    summary = U.apply_plan(plan)
    assert summary.mcp_entries == 1
    assert summary.research_blocks >= 1
    assert not (repo / ".mcp.json").exists()
    assert not (repo / ".agents" / "skills" / "llm-wiki-base-ingest").exists()
    assert not init_project.has_research_block(repo / "AGENTS.md")
    # data wiki còn nguyên
    assert (wiki / "wiki" / "page.md").read_text() == "knowledge"


# ─────────────────────────────────────────────────────────────────────────────
# CLI wiring
# ─────────────────────────────────────────────────────────────────────────────


def test_uninstall_help_lists_examples(runner):
    result = runner.invoke(app, ["uninstall", "--help"])
    assert result.exit_code == 0
    assert "Examples" in result.output


def test_cli_dry_run_touches_nothing(isolated_env, monkeypatch, runner):
    base = isolated_env["base"]
    (base / "tools").mkdir()
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(base / "registry.toml"))
    from llm_wiki_base import registry
    wiki = isolated_env["home"] / "notes"
    _full_personal_wiki(wiki, base)
    registry.add_wiki("notes", str(wiki), wiki_type="personal")

    result = runner.invoke(app, ["uninstall", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert base.exists()
    assert (wiki / ".mcp.json").exists()          # dry-run không đụng gì
    assert "notes" in result.output


def test_cli_yes_removes(isolated_env, monkeypatch, runner):
    base = isolated_env["base"]
    (base / "tools").mkdir()
    monkeypatch.setenv("LLM_WIKI_BASE_REGISTRY", str(base / "registry.toml"))
    from llm_wiki_base import registry
    wiki = isolated_env["home"] / "notes"
    _full_personal_wiki(wiki, base)
    registry.add_wiki("notes", str(wiki), wiki_type="personal")

    result = runner.invoke(app, ["uninstall", "--yes"])
    assert result.exit_code == 0, result.output
    assert not base.exists()
    assert not (wiki / ".mcp.json").exists()
    assert (wiki / "wiki" / "index.md").exists()   # data giữ
    assert "uv tool uninstall llm-wiki-base" in result.output
