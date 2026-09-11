"""Skill installer: copy skills từ package data → `<scope root>/.agents/skills/`.

Nguồn: `src/llm_wiki_base/skills/<subset>/<name>/SKILL.md` — 2 subset:

- ``wiki``     → 7 skill vận hành MỘT wiki (ingest, query, lint, reindex, review,
                 consolidate, translate). Cài vào `<wiki_root>/.agents/skills/`.
- ``codebase`` → `llm-wiki-base-research` (research XUYÊN wiki). Cài vào
                 `<project_root>/.agents/skills/` — root của codebase, KHÔNG phải
                 trong wiki, vì nó cần thấy mọi wiki chứ không chỉ một.

AI tool KHÔNG đọc từ template path — chỉ đọc từ `<root>/.agents/skills/`.
Command Code + các tool theo Agent Skills standard đọc `.agents/skills/` trực tiếp
(nên KHÔNG cần link); Claude Code cần `.claude/skills/`, OpenCode cần
`.opencode/commands/<name>.md` → tạo bằng symlink, xem `link_clients()`.

`.agents/` là canonical: mọi link trỏ VÀO nó. Sửa skill ở link = sửa một lần cho
mọi client. (Layout cũ copy vào `.claude/` rồi link ngược — 2 bản, upgrade sót.)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from llm_wiki_base._package_data import package_path

#: Manifest ghi lại những skill do llm-wiki-base cài — để lần sau prune đúng file của
#: mình, không đụng skill do user tự viết cùng chỗ.
MANIFEST = ".llm-wiki-base-skills.json"

#: Skill đã bị bỏ/gộp ở các bản trước. Xoá khi thấy, kể cả wiki chưa có manifest
#: (wiki cũ không biết mình từng cài gì).
OBSOLETE_PREFIXES = ("wiki-project-", "llm-wiki-base-project-")

#: Client cần link tới `.agents/skills/` vì chúng không đọc chuẩn Agent Skills.
#: commandcode KHÔNG ở đây: nó đọc `.agents/skills/` (project) và `~/.agents/skills/`
#: (user) trực tiếp; tạo `.commandcode/skills/` sẽ bị ưu tiên cao hơn `.agents/`
#: và sinh cảnh báo "Duplicate names" khi hai bản lệch nhau.
CLIENT_LINKS: dict[str, tuple[str, str]] = {
    "claude": (".claude/skills", "dir"),          # symlink -> .agents/skills/<name>/
    "opencode": (".opencode/commands", "flat"),   # symlink -> .agents/skills/<name>/SKILL.md
}

TARGETS = ("universal", "claude", "both", "skip")

#: Mọi skill llm-wiki-base cài đều mang prefix này (wiki + codebase subset).
#: Cùng `OBSOLETE_PREFIXES` là dấu vết để nhận bản của ta khi wiki không có manifest.
OUR_SKILL_PREFIX = "llm-wiki-base-"


def uninstall_skills(root: Path,
                     clients: tuple[str, ...] | list[str] | None = None) -> list[str]:
    """Gỡ TOÀN BỘ skill do llm-wiki-base cài khỏi `root` (ngược của `install_skills`).

    Xoá các skill `llm-wiki-base-*` / prefix obsolete / có trong manifest ở
    `<root>/.agents/skills/`, kèm link của client trỏ vào chúng, rồi xoá manifest.
    KHÔNG đụng skill do user tự viết (không khớp prefix/manifest) và không bao giờ
    xoá nội dung wiki — đây chỉ là footprint của tool.

    Args:
        root: thư mục chứa `.agents/skills/` (wiki root hoặc project root).
        clients: client cần dọn link. Mặc định = mọi client có layout link.

    Returns:
        danh sách tên skill đã gỡ (rỗng nếu không có gì để gỡ).
    """
    skills_dir = root / ".agents" / "skills"
    names = _our_skill_names(skills_dir)
    # Dọn link TRƯỚC khi xoá bản gốc (link trỏ vào skills_dir — xoá trước để giữ
    # resolved path hợp lệ, và không để lại symlink hỏng).
    clients = list(clients) if clients is not None else list(CLIENT_LINKS)
    removed_links = _unlink_clients(root, clients, names)

    removed: list[str] = []
    for name in names:
        target = skills_dir / name
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            continue
        removed.append(name)
    manifest = _manifest_path(skills_dir)
    if manifest.is_file():
        manifest.unlink()

    # Dọn các rỗng để lại (chỉ khi đã không còn gì bên trong).
    if removed or removed_links:
        for rel, _mode in CLIENT_LINKS.values():
            _rmtree_if_empty(root / rel, root)
        _rmtree_if_empty(skills_dir, root)
    return removed


def _our_skill_names(skills_dir: Path) -> list[str]:
    """Tên skill trong `.agents/skills/` được coi là của llm-wiki-base."""
    if not skills_dir.is_dir():
        return []
    managed = set(_manifest_names(skills_dir))
    out: list[str] = []
    for entry in sorted(skills_dir.iterdir()):
        name = entry.name
        if name == MANIFEST:
            continue
        if not (entry.is_dir() or entry.is_symlink()):
            continue
        ours = (name.startswith(OUR_SKILL_PREFIX)
                or name.startswith(OBSOLETE_PREFIXES)
                or name in managed)
        if ours:
            out.append(name)
    return out


def find_our_skills(root: Path,
                    clients: tuple[str, ...] | list[str] | None = None
                    ) -> tuple[list[str], list[Path]]:
    """Preview (read-only): (tên skill của ta, đường dẫn link client của ta) trong `root`.

    Dùng cho dry-run — cùng tiêu chí nhận diện như `uninstall_skills`, không ghi đĩa.
    """
    skills_dir = root / ".agents" / "skills"
    names = _our_skill_names(skills_dir)
    links = _scan_our_links(root, list(clients) if clients is not None
                            else list(CLIENT_LINKS), names)
    return names, links


def _scan_our_links(root: Path, clients: list[str], names: list[str]) -> list[Path]:
    """Đường dẫn link/copy của client trỏ vào skill của ta (read-only)."""
    skills_dir = root / ".agents" / "skills"
    canonical = skills_dir.resolve()
    keep = set(names)
    found: list[Path] = []
    for client in clients:
        layout = CLIENT_LINKS.get(client)
        if not layout:
            continue
        rel, mode = layout
        dst_base = root / rel
        if not dst_base.is_dir():
            continue
        for entry in sorted(dst_base.iterdir()):
            skill_name = entry.name[:-3] if mode == "flat" else entry.name
            points_at_us = False
            if entry.is_symlink():
                resolved = (entry.parent / entry.readlink()).resolve()
                points_at_us = resolved.is_relative_to(canonical)
            is_ours = points_at_us or skill_name in keep or skill_name.startswith(
                (OUR_SKILL_PREFIX, *OBSOLETE_PREFIXES))
            if is_ours and (entry.is_symlink() or entry.is_file() or entry.is_dir()):
                found.append(entry)
    return found


def _unlink_clients(root: Path, clients: list[str], names: list[str]) -> int:
    """Xoá link/copy của client trỏ vào skill của ta. Trả số link đã xoá."""
    skills_dir = root / ".agents" / "skills"
    canonical = skills_dir.resolve()
    keep = set(names)
    removed = 0
    for client in clients:
        layout = CLIENT_LINKS.get(client)
        if not layout:
            continue
        rel, mode = layout
        dst_base = root / rel
        if not dst_base.is_dir():
            continue
        for entry in sorted(dst_base.iterdir()):
            skill_name = entry.name[:-3] if mode == "flat" else entry.name
            points_at_us = False
            if entry.is_symlink():
                resolved = (entry.parent / entry.readlink()).resolve()
                points_at_us = resolved.is_relative_to(canonical)
            is_ours = points_at_us or skill_name in keep or skill_name.startswith(
                (OUR_SKILL_PREFIX, *OBSOLETE_PREFIXES))
            if not is_ours:
                continue
            if entry.is_symlink() or entry.is_file():
                entry.unlink(missing_ok=True)
            elif entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                continue
            removed += 1
    return removed


def _rmtree_if_empty(path: Path, stop_at: Path) -> None:
    """Xoá `path` nếu nó rỗng (kể cả chỉ còn .DS_Store), rồi thử dọn cha tới `stop_at`."""
    try:
        p = path.resolve()
        stop = stop_at.resolve()
    except OSError:
        return
    while p != stop and p.is_dir():
        leftover = [c for c in p.iterdir() if c.name != ".DS_Store"]
        if leftover:
            return
        try:
            p.rmdir()
        except OSError:
            return
        p = p.parent


def available_skills(subset: str) -> list[str]:
    """Tên skill có trong package data cho một subset ('wiki' | 'codebase' | 'all')."""
    out: list[str] = []
    for sub in _expand(subset):
        base = package_path("skills", sub)
        if not base.is_dir():
            continue
        out += sorted(d.name for d in base.iterdir() if (d / "SKILL.md").exists())
    return out


def install_skills(
    root: Path,
    target: str,
    subset: str = "wiki",
    clients: tuple[str, ...] | list[str] = (),
) -> list[str]:
    """Copy skills của `subset` vào `<root>/.agents/skills/` rồi link cho `clients`.

    Args:
        root: thư mục sẽ chứa `.agents/skills/` (wiki root, hoặc project root cho
            subset `codebase`).
        target: 'universal' | 'claude' | 'both' | 'skip'.
            `claude`/`both` = thêm link cho client tương ứng ngay cả khi `clients` rỗng.
        subset: 'wiki' | 'codebase' | 'all'.
        clients: tên client cần link ('claude', 'opencode', ...). Client không có
            layout link (vd commandcode) được bỏ qua im lặng.

    Returns:
        danh sách skill name đã cài.

    Raises:
        ValueError: `target` không hợp lệ (trước đây giá trị lạ âm thầm trả [] rồi
            in "skills source not found" — thông điệp sai lệch).
    """
    if target not in TARGETS:
        raise ValueError(f"skills-target phải là một trong {TARGETS}, nhận: {target!r}")
    if target == "skip":
        return []

    skills_dir = root / ".agents" / "skills"
    # Đọc manifest TRƯỚC khi copy — copy ghi đè nó, prune cần biết bản trước cài gì.
    previously_installed = _manifest_names(skills_dir)
    wanted = _copy_subset(subset, skills_dir)
    if not wanted:
        return []

    removed = _prune(skills_dir, wanted, previously_installed)
    if removed:
        print(f"  pruned {len(removed)} skill không còn trong package: "
              f"{', '.join(removed)}")

    want = set(clients)
    if target in ("claude", "both"):
        want |= {"claude"} if target == "claude" else {"claude", "opencode"}
    link_clients(root, sorted(want), wanted)
    return wanted


def link_clients(root: Path, clients: list[str] | tuple[str, ...],
                 names: list[str] | None = None) -> list[Path]:
    """Tạo project-level symlink cho từng client trong `clients`.

    Port của `base_scripts/link_skills.sh` sang Python: cùng hành vi (dir symlink
    cho Claude, flat `.md` symlink cho OpenCode, prune link chết), nhưng chạy được
    trên Windows (fallback copy) và không phụ thuộc bash. Script .sh đã xoá vì nó
    tính REPO_ROOT theo vị trí chính nó → vô dụng sau khi `base install` copy vào
    `~/.llm-wiki-base/scripts/`, và chưa từng được gọi từ code nào.
    """
    skills_dir = root / ".agents" / "skills"
    names = names or _manifest_names(skills_dir)
    made: list[Path] = []
    for client in clients:
        layout = CLIENT_LINKS.get(client)
        if not layout or not names:
            continue
        rel, mode = layout
        dst_base = root / rel
        dst_base.mkdir(parents=True, exist_ok=True)
        for name in names:
            src = skills_dir / name
            if not src.is_dir():
                continue
            link = dst_base / (f"{name}.md" if mode == "flat" else name)
            made.append(_make_link(link, src, mode, client))
        _prune_links(dst_base, skills_dir, mode, names)
    return made


# ─────────────────────────────────────────────────────────── internals

def _expand(subset: str) -> list[str]:
    return ["wiki", "codebase"] if subset == "all" else [subset]


def _copy_subset(subset: str, dst_base: Path) -> list[str]:
    copied: list[str] = []
    for sub in _expand(subset):
        src_base = package_path("skills", sub)
        if not src_base.is_dir():
            continue
        for skill_dir in sorted(src_base.iterdir()):
            if not (skill_dir / "SKILL.md").is_file():
                continue
            copied += [_copy_one(skill_dir, dst_base)]
    _write_manifest(dst_base, copied)
    return copied


def _copy_one(skill_dir: Path, dst_base: Path) -> str:
    dst = dst_base / skill_dir.name
    dst.mkdir(parents=True, exist_ok=True)      # exist_ok cả khi dst là symlink→dir
    shutil.copy2(skill_dir / "SKILL.md", dst / "SKILL.md")
    for extra in skill_dir.iterdir():           # scripts/, references/… nếu có
        if extra.name == "SKILL.md":
            continue
        t = dst / extra.name
        if extra.is_file():
            shutil.copy2(extra, t)
        elif extra.is_dir():
            shutil.rmtree(t, ignore_errors=True)
            shutil.copytree(extra, t)
    return skill_dir.name


def _make_link(link: Path, src: Path, mode: str, client: str) -> Path:
    """Idempotent: xoá link cũ rồi tạo lại (trỏ đúng src hiện tại)."""
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        # Real dir/file: có thể là bản copy của layout CŨ (`.claude/skills/` từng là
        # canonical) → thay bằng symlink để chỉ còn MỘT bản. Không bao giờ xoá thứ
        # ta không nhận ra: giữ nguyên nếu trong đó có SKILL.md khác nội dung.
        if _is_ours(link, src, mode):
            shutil.rmtree(link) if link.is_dir() else link.unlink()
        else:
            print(f"  ! {client}: giữ nguyên {link} "
                  f"(không phải bản do llm-wiki-base cài) — skill này KHÔNG được link.")
            return link
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        if mode == "flat":
            link.symlink_to((src / "SKILL.md").resolve())
        else:
            link.symlink_to(src.resolve(), target_is_directory=True)
    except (OSError, NotImplementedError):
        # Windows: symlink cần Developer Mode → fallback copy
        if mode == "flat":
            shutil.copy2(src / "SKILL.md", link)
        else:
            shutil.copytree(src, link)
    return link


def _is_ours(link: Path, src: Path, mode: str) -> bool:
    """Link/dir này do llm-wiki-base ghi ra? = nội dung khớp bản trong `.agents/skills/`."""
    try:
        mine = (src / "SKILL.md").read_bytes()
        theirs = ((link / "SKILL.md") if mode == "dir" else link).read_bytes()
    except OSError:
        return False
    return mine == theirs


def _prune_links(dst_base: Path, skills_dir: Path, mode: str, names: list[str]) -> None:
    """Xoá symlink trỏ vào skills không còn tồn tại / không thuộc subset này.

    Chỉ xoá link mà CHÍNH nó trỏ vào `.agents/skills/` — link của user trỏ chỗ khác
    thì không đụng tới.
    """
    if not dst_base.is_dir():
        return
    keep = set(names)
    canonical = skills_dir.resolve()
    for entry in sorted(dst_base.iterdir()):
        if not entry.is_symlink():
            continue
        skill_name = entry.name[:-3] if mode == "flat" else entry.name
        resolved = (entry.parent / entry.readlink()).resolve()
        if not resolved.is_relative_to(canonical):
            continue                      # link tay trỏ ra ngoài — không phải của ta
        if skill_name not in keep or not (skills_dir / skill_name).is_dir():
            entry.unlink()


def _prune(skills_dir: Path, wanted: list[str],
           previously_installed: list[str]) -> list[str]:
    """Xoá skill do llm-wiki-base cài mà bản này không còn ship. Không đụng skill của user."""
    if not skills_dir.is_dir():
        return []
    keep = set(wanted)
    managed = set(previously_installed)
    removed: list[str] = []
    for entry in sorted(skills_dir.iterdir()):
        name = entry.name
        if name in keep or name == MANIFEST:
            continue
        if not (entry.is_dir() or entry.is_symlink()):
            continue
        # Hoặc là tên cũ đã biết (wiki cũ chưa từng có manifest), hoặc do ta cài trước.
        if not (name.startswith(OBSOLETE_PREFIXES) or name in managed):
            continue
        if entry.is_symlink():
            entry.unlink()
        else:
            shutil.rmtree(entry)
        removed.append(name)
    return removed


def _manifest_path(skills_dir: Path) -> Path:
    return skills_dir / MANIFEST


def _write_manifest(skills_dir: Path, names: list[str]) -> None:
    """Ghi danh sách skill DO TA cài — lần sau chỉ những thứ này mới được prune."""
    _manifest_path(skills_dir).write_text(
        json.dumps({"skills": sorted(set(names)), "version": 1}, indent=2) + "\n",
        encoding="utf-8",
    )


def _manifest_names(skills_dir: Path) -> list[str]:
    p = _manifest_path(skills_dir)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    names = data.get("skills", [])
    return [n for n in names if isinstance(n, str)]
