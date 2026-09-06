"""Tests cho `llm-wiki-base upgrade --to <tag|latest>` (GitHub tags vX.Y.Z)."""

import subprocess
from pathlib import Path

from llm_wiki_base import upgrade as U
from llm_wiki_base.cli import app


def _git(dir: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(dir), *args], check=True, capture_output=True)


def _fake_core(tmp_path: Path, *tags: str) -> Path:
    core = tmp_path / "core"
    core.mkdir()
    _git(core, "init")
    _git(core, "config", "user.email", "t@t.t")
    _git(core, "config", "user.name", "t")
    (core / "f.txt").write_text("x")
    _git(core, "add", ".")
    _git(core, "commit", "-m", "init")
    for i, tag in enumerate(tags):
        (core / "f.txt").write_text(f"{tag}-{i}")
        _git(core, "add", ".")
        _git(core, "commit", "-m", tag)
        _git(core, "tag", tag)
    return core


def test_parse_tag():
    assert U.parse_tag("v1.2.3") == (1, 2, 3)
    assert U.parse_tag("v1.2.3^{}") == (1, 2, 3)
    assert U.parse_tag("1.2.3") is None
    assert U.parse_tag("latest") is None
    assert U.parse_tag("v1.2") is None


def test_latest_prefers_newest_local(tmp_path):
    core = _fake_core(tmp_path, "v0.1.0", "v0.10.0", "v0.2.0")
    assert U.latest_tag(core) == "v0.10.0"  # sort semver, không sort chuỗi
    assert U.resolve_target(core, "latest") == "v0.10.0"
    assert U.resolve_target(core, "v0.1.0") == "v0.1.0"
    assert U.resolve_target(core, "v9.9.9") is None
    assert U.resolve_target(core, "bogus") is None
    assert U.core_tag(core) == "v0.2.0"  # HEAD ở tag cuối, còn latest là max semver


def test_no_tags(tmp_path):
    core = _fake_core(tmp_path)
    assert U.latest_tag(core) is None
    assert U.core_tag(core) is None


def _fake_wiki(base: Path, name: str = "w") -> Path:
    wiki = base / name
    (wiki / ".agents" / "skills" / "old-skill").mkdir(parents=True)
    (wiki / ".agents" / "skills" / "old-skill" / "SKILL.md").write_text("old")
    (wiki / "AGENTS.md").write_text("stale", encoding="utf-8")
    return wiki


def test_backup_version_roundtrip(tmp_path):
    wiki = _fake_wiki(tmp_path)
    assert U.read_version(wiki) is None
    backup = U.backup_wiki(wiki, ts="ts1")
    assert backup is not None
    assert (backup / "AGENTS.md").read_text() == "stale"
    assert (backup / ".agents/skills/old-skill/SKILL.md").read_text() == "old"
    U.write_version(wiki, "v0.2.0")
    assert U.read_version(wiki) == "v0.2.0"


def test_backup_empty_wiki(tmp_path):
    wiki = tmp_path / "empty"
    wiki.mkdir()
    assert U.backup_wiki(wiki) is None  # không có gì managed → không backup rỗng


def test_sync_agent_configs_overwrites(tmp_path):
    wiki = _fake_wiki(tmp_path)
    done = U.sync_agent_configs(wiki)
    assert "AGENTS.md" in done
    assert (wiki / "AGENTS.md").read_text(encoding="utf-8") != "stale"


def test_upgrade_dry_run_cli(runner, isolated_env, tmp_path, monkeypatch):
    from llm_wiki_base import registry

    core = _fake_core(tmp_path, "v0.1.0")
    monkeypatch.setattr(U, "find_core", lambda: core)
    wiki = _fake_wiki(tmp_path / "wikis")
    registry.add_wiki("demo", str(wiki))
    result = runner.invoke(app, ["upgrade", "--to", "latest", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "v0.1.0" in result.output
    assert U.read_version(wiki) is None  # dry-run không ghi VERSION


def test_upgrade_apply_cli(runner, isolated_env, tmp_path, monkeypatch):
    from llm_wiki_base import registry

    core = _fake_core(tmp_path, "v0.1.0")
    monkeypatch.setattr(U, "find_core", lambda: core)
    wiki = _fake_wiki(tmp_path / "wikis")
    registry.add_wiki("demo", str(wiki))
    result = runner.invoke(app, ["upgrade", "--to", "v0.1.0"])
    assert result.exit_code == 0, result.output
    assert U.read_version(wiki) == "v0.1.0"
    assert (wiki / ".llm-wiki-base" / "backups").is_dir()  # backup + overwrite
    assert (wiki / "AGENTS.md").read_text(encoding="utf-8") != "stale"
    assert (wiki / ".agents" / "skills").is_dir()  # install_skills đã chạy


def test_upgrade_unknown_wiki(runner, isolated_env, tmp_path, monkeypatch):
    core = _fake_core(tmp_path, "v0.1.0")
    monkeypatch.setattr(U, "find_core", lambda: core)
    result = runner.invoke(app, ["upgrade", "--to", "v0.1.0", "--wiki", "nope"])
    assert result.exit_code == 1


def test_upgrade_core_not_on_tag(runner, isolated_env, tmp_path, monkeypatch):
    from llm_wiki_base import registry

    core = _fake_core(tmp_path, "v0.1.0")
    (core / "new.txt").write_text("new")  # commit mới sau tag → core lệch tag
    _git(core, "add", ".")
    _git(core, "commit", "-m", "after tag")
    monkeypatch.setattr(U, "find_core", lambda: core)
    wiki = _fake_wiki(tmp_path / "wikis")
    registry.add_wiki("demo", str(wiki))
    result = runner.invoke(app, ["upgrade", "--to", "v0.1.0"])
    assert result.exit_code == 1  # từ chối + in hướng dẫn checkout
    assert "checkout" in result.output


def _fake_project(base: Path) -> tuple[Path, Path]:
    root = base / "proj"
    wiki = root / "wiki"
    (wiki / ".agents" / "skills").mkdir(parents=True)
    research = root / ".agents" / "skills" / "llm-wiki-base-research"
    research.mkdir(parents=True)
    (research / "SKILL.md").write_text("stale-root", encoding="utf-8")
    return root, wiki


def test_find_project_root(tmp_path):
    root, wiki = _fake_project(tmp_path)
    assert U.find_project_root(wiki) == root.resolve()
    assert U.find_project_root(tmp_path / "lonely") is None


def test_upgrade_project_root_apply(runner, isolated_env, tmp_path, monkeypatch):
    from llm_wiki_base import registry
    from llm_wiki_base._package_data import package_path

    core = _fake_core(tmp_path, "v0.1.0")
    monkeypatch.setattr(U, "find_core", lambda: core)
    root, wiki = _fake_project(tmp_path / "work")
    registry.add_wiki("proj", str(wiki), "project")
    result = runner.invoke(app, ["upgrade", "--to", "v0.1.0"])
    assert result.exit_code == 0, result.output
    assert U.read_version(root) == "v0.1.0"  # root cũng được stamp
    assert (root / ".llm-wiki-base" / "backups").is_dir()  # root có backup riêng
    fresh = package_path("skills", "codebase", "llm-wiki-base-research",
                         "SKILL.md").read_text(encoding="utf-8")
    assert (root / ".agents" / "skills" / "llm-wiki-base-research" / "SKILL.md"
            ).read_text(encoding="utf-8") == fresh
    assert "root" in result.output


def test_upgrade_project_without_root(runner, isolated_env, tmp_path, monkeypatch):
    from llm_wiki_base import registry

    core = _fake_core(tmp_path, "v0.1.0")
    monkeypatch.setattr(U, "find_core", lambda: core)
    wiki = _fake_wiki(tmp_path / "work")
    registry.add_wiki("proj", str(wiki), "project")
    result = runner.invoke(app, ["upgrade", "--to", "v0.1.0"])
    assert result.exit_code == 0, result.output  # wiki vẫn upgrade dù thiếu root
    assert U.read_version(wiki) == "v0.1.0"


def test_personal_ignores_ancestor_root(runner, isolated_env, tmp_path, monkeypatch):
    from llm_wiki_base import registry

    core = _fake_core(tmp_path, "v0.1.0")
    monkeypatch.setattr(U, "find_core", lambda: core)
    root, wiki = _fake_project(tmp_path / "work")
    registry.add_wiki("me", str(wiki))  # personal → không đụng root
    result = runner.invoke(app, ["upgrade", "--to", "v0.1.0"])
    assert result.exit_code == 0, result.output
    assert U.read_version(root) is None
    assert (root / ".agents" / "skills" / "llm-wiki-base-research" / "SKILL.md"
            ).read_text(encoding="utf-8") == "stale-root"
