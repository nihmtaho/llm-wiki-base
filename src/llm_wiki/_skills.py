"""Per-wiki skill installer: copy skills từ package data → <wiki>/.agents/skills/.

Skills ở template `src/llm_wiki/skills/{personal,project}/<name>/SKILL.md` chỉ là
source để `llm-wiki init` copy vào per-wiki dir. AI tool KHÔNG đọc từ template
path — chỉ đọc từ `<wiki>/.agents/skills/`.
"""
import shutil
from pathlib import Path

from llm_wiki._package_data import package_path


def install_skills(wiki_root: Path, target: str, base_skills_dir: str) -> list[str]:
    """Copy skills từ package data → <wiki>/.agents/skills/ (và optional .claude/skills/).

    Args:
        wiki_root: wiki root dir.
        target: 'universal' | 'claude' | 'both' | 'skip'.
        base_skills_dir: 'personal' | 'project'.

    Returns:
        list of skill names đã install.
    """
    if target == "skip":
        return []

    src_base = package_path("skills", base_skills_dir)
    if not src_base.is_dir():
        return []

    universal_skills = wiki_root / ".agents" / "skills"
    claude_skills = wiki_root / ".claude" / "skills"
    installed: list[str] = []

    if target in ("universal", "both"):
        universal_skills.mkdir(parents=True, exist_ok=True)
        installed = _copy_skills_to_dir(src_base, universal_skills)

    if target == "claude":
        # Copy vào .claude/skills/, symlink .agents/skills/<name> → .claude/skills/<name>
        claude_skills.mkdir(parents=True, exist_ok=True)
        installed = _copy_skills_to_dir(src_base, claude_skills)
        universal_skills.mkdir(parents=True, exist_ok=True)
        for skill_dir in claude_skills.iterdir():
            if not skill_dir.is_dir():
                continue
            link = universal_skills / skill_dir.name
            if link.exists() or link.is_symlink():
                continue
            try:
                link.symlink_to(skill_dir.resolve())
            except OSError:
                # Windows no symlink privilege → fallback copy
                shutil.copytree(skill_dir, link, dirs_exist_ok=True)

    if target == "both":
        claude_skills.mkdir(parents=True, exist_ok=True)
        _copy_skills_to_dir(src_base, claude_skills)

    return installed


def _copy_skills_to_dir(src_base: Path, dst_base: Path) -> list[str]:
    """Copy mỗi <name>/SKILL.md (và scripts/) từ src_base → dst_base. Idempotent.

    Returns list of skill names copied.
    """
    installed: list[str] = []
    for skill_dir in src_base.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        dst = dst_base / skill_dir.name
        dst.mkdir(parents=True, exist_ok=True)
        # Overwrite SKILL.md (idempotent)
        shutil.copy2(skill_md, dst / "SKILL.md")
        # Copy additional files (scripts/, etc.) nếu có
        for f in skill_dir.iterdir():
            if f.name == "SKILL.md":
                continue
            target = dst / f.name
            if f.is_file():
                shutil.copy2(f, target)
            elif f.is_dir():
                shutil.copytree(f, target, dirs_exist_ok=True)
        installed.append(skill_dir.name)
    return installed
