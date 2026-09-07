"""Upgrade wikis đã đăng ký lên tag GitHub mới (`vX.Y.Z`).

Cơ chế tối giản — không manifest/checksum tay:
- Tag mới nhất: `git ls-remote --tags origin` (fallback tag local khi offline).
- Skills: backup `.agents/skills/` rồi chạy lại `install_skills` (ghi đè + prune
  obsolete — cùng hàm `init` dùng, nên không lệch hành vi).
- Agent configs (`AGENTS.md`, `_schema.md`, `.claude/CLAUDE.md`): backup rồi ghi đè
  từ `templates/agents/` (`init` chỉ copy khi chưa có nên không reuse được).
- State mỗi wiki: 1 dòng tag trong `.llm-wiki-base/VERSION`.
- Wiki loại `project` còn có skill `codebase` cài ở project root
  (`<root>/.agents/skills/`): tự tìm root (ancestor gần nhất có codebase skill
  đã cài), backup + sync + stamp VERSION ở root luôn (cùng timestamp backup).
- Rollback = `upgrade --to <tag-cũ>` (core checkout tag đó trước) hoặc chép ngược
  từ `.llm-wiki-base/backups/<ts>/`.

Source file luôn lấy từ core ĐANG CHẠY (package data), không `git show` từ tag:
`--to` phải trùng tag core đang checkout, nếu không lệnh in hướng dẫn checkout.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
VERSION_FILE = ".llm-wiki-base/VERSION"
BACKUP_KEEP = 5

#: Thư mục skills trong wiki (đích của `install_skills(..., subset="wiki")`).
SKILLS_DIR = Path(".agents/skills")

#: (template, đích trong wiki) cho agent configs.
AGENT_FILES = (
    ("AGENTS.md", "AGENTS.md"),
    ("_schema.md", "_schema.md"),
    ("CLAUDE.md", ".claude/CLAUDE.md"),
)

#: Source trong core tương ứng — chỉ dùng cho `git diff` khi `--dry-run`.
SRC_DIRS = ("src/llm_wiki_base/skills", "src/llm_wiki_base/templates/agents")


def parse_tag(tag: str) -> tuple[int, int, int] | None:
    """`v1.2.3` -> (1, 2, 3); sai quy ước -> None."""
    m = TAG_RE.match(tag.strip().removesuffix("^{}"))
    return tuple(int(g) for g in m.groups()) if m else None  # type: ignore[return-value]


def _git(core: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(core), *args],
        capture_output=True,
        timeout=30,
    )


def find_core() -> Path | None:
    """Thư mục `.git` chứa package này (None khi chạy ngoài checkout)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    return None


def local_tags(core: Path) -> list[str]:
    """Tags `vX.Y.Z` có sẵn ở local (không cần mạng)."""
    proc = _git(core, "tag", "--list", "v*")
    if proc.returncode != 0:
        return []
    tags = [t for t in proc.stdout.decode().split() if parse_tag(t)]
    return sorted(tags, key=parse_tag)  # type: ignore[arg-type]


def latest_tag(core: Path) -> str | None:
    """Tag mới nhất: thử `fetch` remote (best-effort), so trên hợp local+remote."""
    try:
        _git(core, "fetch", "--tags", "origin")
    except (OSError, subprocess.SubprocessError):
        pass
    proc = _git(core, "ls-remote", "--tags", "origin")
    remote = (
        [t.split("refs/tags/")[-1] for t in proc.stdout.decode().split() if "refs/tags/" in t]
        if proc.returncode == 0
        else []
    )
    known = [t for t in {*local_tags(core), *remote} if parse_tag(t)]
    return max(known, key=parse_tag) if known else None  # type: ignore[arg-type]


def core_tag(core: Path) -> str | None:
    """Tag core đang checkout (`git describe --exact-match`), None nếu lệch/không tag."""
    proc = _git(core, "describe", "--tags", "--exact-match")
    tag = proc.stdout.decode().strip() if proc.returncode == 0 else ""
    return tag if parse_tag(tag) else None


def resolve_target(core: Path, to: str) -> str | None:
    """`latest` -> tag mới nhất; tag cụ thể -> verify tồn tại local. None = không xong."""
    if to == "latest":
        return latest_tag(core)
    to = to.strip()
    if not parse_tag(to):
        return None
    if to not in local_tags(core):  # có thể tag mới chưa fetch
        try:
            _git(core, "fetch", "--tags", "origin")
        except (OSError, subprocess.SubprocessError):
            pass
        if to not in local_tags(core):
            return None
    return to


def read_version(wiki: Path) -> str | None:
    """Tag wiki đang ở (None khi chưa từng upgrade)."""
    try:
        tag = (wiki / VERSION_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return tag if parse_tag(tag) else None


def write_version(wiki: Path, tag: str) -> None:
    path = wiki / VERSION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tag + "\n", encoding="utf-8")


def managed_targets(wiki: Path) -> list[Path]:
    """Các file/dir managed HIỆN CÓ trong wiki (để backup)."""
    found = []
    if (wiki / SKILLS_DIR).is_dir():
        found.append(SKILLS_DIR)
    for _, dst in AGENT_FILES:
        if (wiki / dst).is_file():
            found.append(Path(dst))
    return found


def backup_wiki(wiki: Path, ts: str | None = None) -> Path | None:
    """Copy managed hiện có vào `.llm-wiki-base/backups/<ts>/`, tỉa giữ 5 bản."""
    targets = managed_targets(wiki)
    if not targets:
        return None
    ts = ts or datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = wiki / ".llm-wiki-base" / "backups" / ts
    for rel in targets:
        src = wiki / rel
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, out, symlinks=True)
        else:
            shutil.copy2(src, out)
    backups = wiki / ".llm-wiki-base" / "backups"
    for old in sorted(backups.iterdir())[:-BACKUP_KEEP]:
        shutil.rmtree(old, ignore_errors=True)
    return dest


def sync_agent_configs(wiki: Path) -> list[str]:
    """Ghi đè agent configs từ templates (ngược với init: init bỏ qua file có sẵn)."""
    from llm_wiki_base._package_data import read_template, template_exists

    done = []
    for name, dst in AGENT_FILES:
        if not template_exists("templates", "agents", name):
            continue
        path = wiki / dst
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(read_template("templates", "agents", name), encoding="utf-8")
        done.append(dst)
    return done


def sync_skills(wiki: Path) -> list[str]:
    """Chạy lại `install_skills` như `init` (ghi đè + prune obsolete + manifest)."""
    from llm_wiki_base._skills import install_skills

    return install_skills(wiki, target="universal", subset="wiki", clients=())


#: Tìm project root tối đa mấy tầng trên wiki dir.
ROOT_SEARCH_DEPTH = 3


def _codebase_names() -> set[str]:
    """Tên skill subset `codebase` trong core (nguồn xác định project root)."""
    from llm_wiki_base._package_data import package_path

    src = package_path("skills", "codebase")
    if not src.is_dir():
        return set()
    return {p.name for p in src.iterdir() if p.is_dir()}


def find_project_root(wiki: Path) -> Path | None:
    """Ancestor gần nhất (≤3 tầng trên wiki) có codebase skill đã cài."""
    wanted = _codebase_names()
    if not wanted:
        return None
    for parent in list(wiki.resolve().parents)[:ROOT_SEARCH_DEPTH]:
        skills = parent / ".agents" / "skills"
        if any((skills / name).is_dir() for name in wanted):
            return parent
    return None


def sync_codebase(root: Path) -> list[str]:
    """Chạy lại `install_skills(..., subset="codebase")` ở project root."""
    from llm_wiki_base._skills import install_skills

    return install_skills(root, target="universal", subset="codebase", clients=())


def backup_root_skills(root: Path, ts: str) -> Path | None:
    """Backup `.agents/skills` của root vào `<root>/.llm-wiki-base/backups/<ts>/`."""
    if not (root / SKILLS_DIR).is_dir():
        return None
    ts_dir = root / ".llm-wiki-base" / "backups" / ts
    dest = ts_dir / SKILLS_DIR
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / SKILLS_DIR, dest, symlinks=True)
    for old in sorted((root / ".llm-wiki-base" / "backups").iterdir())[:-BACKUP_KEEP]:
        shutil.rmtree(old, ignore_errors=True)
    return ts_dir


def changed_sources(core: Path, old: str | None, new: str) -> list[str] | None:
    """Map `git diff old new` (source core) sang path wiki-relative (cho --dry-run).

    None khi không diff được (chưa từng upgrade / thiếu git) → dry-run báo gộp.
    """
    if old is None or old == new:
        return [] if old == new else None
    proc = _git(core, "diff", "--name-only", old, new, "--", *SRC_DIRS)
    if proc.returncode != 0:
        return None
    mapped = []
    for line in proc.stdout.decode().splitlines():
        line = line.strip()
        if line.startswith("src/llm_wiki_base/skills/"):
            rest = line.split("src/llm_wiki_base/skills/", 1)[1].split("/", 2)
            if len(rest) == 3:  # <subset>/<skill>/<file...>
                mapped.append(str(Path(".agents/skills") / rest[1] / rest[2]))
        elif line.startswith("src/llm_wiki_base/templates/agents/"):
            name = line.rsplit("/", 1)[1]
            for src_name, dst in AGENT_FILES:
                if name == src_name:
                    mapped.append(dst)
    return sorted(set(mapped))


def upgrade_wiki(wiki: Path, tag: str, dry_run: bool = False,
                 wiki_type: str = "personal") -> dict:
    """Backup + sync 1 wiki (+ project root nếu type `project`).

    Trả dict {old, new, backup, skills, configs, changed, root, applied}.
    """
    old = read_version(wiki)
    root_info: dict | None = None
    if wiki_type == "project":
        root = find_project_root(wiki)
        if root is not None:
            root_info = {"path": str(root), "old": read_version(root),
                         "new": tag, "backup": None, "skills": [],
                         "applied": False}
    if dry_run:
        return {"old": old, "new": tag, "backup": None, "skills": [], "configs": [],
                "changed": None, "root": root_info, "applied": False}
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_wiki(wiki, ts=ts)
    skills = sync_skills(wiki)
    configs = sync_agent_configs(wiki)
    write_version(wiki, tag)
    if root_info is not None:
        root = Path(root_info["path"])
        root_info["backup"] = backup_root_skills(root, ts)
        root_info["skills"] = sync_codebase(root)
        write_version(root, tag)
        root_info["applied"] = True
    return {"old": old, "new": tag, "backup": backup, "skills": skills,
            "configs": configs, "changed": None, "root": root_info,
            "applied": True}


def upgrade_all(core: Path, tag: str, wiki_name: str | None = None,
                dry_run: bool = False) -> dict:
    """Upgrade mọi wiki trong registry (hoặc 1 wiki)."""
    from llm_wiki_base import registry

    entries = [registry.find(wiki_name)] if wiki_name else registry.list_wikis()
    if wiki_name and not entries[0]:
        return {"tag": tag, "done": [], "missing": [], "unknown": [wiki_name]}
    done, missing = [], []
    for entry in entries:
        if entry is None:
            continue
        path = Path(entry.get("path", "")).expanduser()
        if not path.is_dir():
            missing.append(entry.get("name", "?"))
            continue
        result = upgrade_wiki(path, tag, dry_run=dry_run,
                              wiki_type=entry.get("type", "personal"))
        if dry_run:
            result["changed"] = changed_sources(core, result["old"], tag)
        result.update({"name": entry.get("name", "?"), "path": str(path)})
        done.append(result)
    return {"tag": tag, "done": done, "missing": missing, "unknown": []}
