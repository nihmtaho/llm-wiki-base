"""`llm-wiki-base uninstall` — dọn footprint của TOOL khỏi máy, GIỮ NGUYÊN dữ liệu wiki.

Triết lý: uninstall xoá những gì llm-wiki-base TỰ ghi ra, không xoá kiến thức mà
con người/AI đã ingest. Phân biệt rõ hai loại:

FOOTPRINT (bị gỡ):
  - Global runtime `~/.llm-wiki-base/` (tools/ rag/ scripts/ .venv/ templates/
    requirements.txt registry.toml). Đọc registry TRƯỚC khi xoá để biết còn wiki nào.
  - MCP server entry của ta trong file config per-project/personal wiki
    (`.mcp.json`, `opencode.jsonc`, …) — gỡ đúng entry của ta, giữ server khác.
  - Skill `llm-wiki-base-*` + link client (`.claude/skills/`, `.opencode/commands/`)
    mà ta cài, và manifest `.llm-wiki-base-skills.json`.
  - Block research đã marker trong `AGENTS.md` / `.claude/CLAUDE.md` ở project root.
  - Thư mục state `.llm-wiki-base/` (VERSION + backups do tool tạo) trong mỗi wiki.

GIỮ LẠI (dữ liệu wiki — tuyệt đối không đụng):
  raw/ wiki/ rag/ eval/ AGENTS.md _schema.md .llm-wiki-base.toml .gitignore .env,
  cùng mọi skill/file của user không khớp dấu vết của ta.

Vì project wiki cài MCP + codebase skill ở REPO ROOT (không phải wiki subdir),
plan tách làm hai loại đích: `WikiTarget` (chỉ thư mục wiki) và `SharedTarget`
(mỗi repo root đúng MỘT lần, kể cả khi nhiều wiki cùng nằm trong đó) — không có
chuyện hai wiki cùng đòi dọn một chỗ.

`uninstall` chỉ dọn phần nó ghi xuống ĐĨA; bản thân package Python (`uv tool` /
`pip`) không tự gỡ được khi đang chạy, nên lệnh in ra chỉ dẫn gỡ CLI sau cùng.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from llm_wiki_base.base import get_base_dir
from llm_wiki_base.config import (
    get_mcp_config_path,
    get_project_mcp_path,
    supported_clients,
)
from llm_wiki_base.installer import find_our_mcp_entries, remove_our_mcp_entries
from llm_wiki_base.registry import get_registry_path, list_wikis

#: Số tầng cha tối đa được quét cho footprint của project wiki — khớp
#: `upgrade.ROOT_SEARCH_DEPTH`, vì project MCP + codebase skill nằm ở repo root.
ROOT_SEARCH_DEPTH = 3

#: Thư mục skills canonical (mọi link client trỏ vào đây).
AGENTS_SKILLS = Path(".agents") / "skills"

#: Agent files có thể mang block research do `init project` ghi ở repo root.
RESEARCH_RELS = ("AGENTS.md", ".claude/CLAUDE.md")

#: Thư mục state của tool trong wiki (VERSION + backups) — không phải kiến thức.
STATE_DIR = ".llm-wiki-base"


@dataclass
class McpRemoval:
    client: str
    path: Path
    names: list[str]
    scope: str  # 'project' | 'user'


@dataclass
class SkillsRemoval:
    root: Path
    names: list[str]
    links: list[Path]


@dataclass
class WikiTarget:
    """Footprint nằm TRONG một wiki dir (skills subset `wiki`, state dir, MCP nếu
    file config nằm ngay trong wiki — case personal wiki)."""

    name: str
    path: Path
    mcp: list[McpRemoval] = field(default_factory=list)
    skills: list[SkillsRemoval] = field(default_factory=list)
    research_files: list[Path] = field(default_factory=list)
    state_dir: Path | None = None

    def is_empty(self) -> bool:
        return not (self.mcp or self.skills or self.research_files
                    or self.state_dir)


@dataclass
class SharedTarget:
    """Footprint ở một repo root CHUNG cho nhiều project wiki: codebase skills +
    MCP + block research (+ state dir mà `upgrade` stamp ở root). Mỗi root chỉ
    xuất hiện một lần trong plan."""

    path: Path
    wikis: list[str] = field(default_factory=list)
    mcp: list[McpRemoval] = field(default_factory=list)
    skills: list[SkillsRemoval] = field(default_factory=list)
    research_files: list[Path] = field(default_factory=list)
    state_dir: Path | None = None

    def is_empty(self) -> bool:
        return not (self.mcp or self.skills or self.research_files
                    or self.state_dir)


@dataclass
class Plan:
    base_dir: Path
    base_exists: bool
    #: registry.toml — thường nằm trong base, nhưng env `LLM_WIKI_BASE_REGISTRY`
    #: trỏ ra ngoài được → phải nhớ path riêng để dọn nốt.
    registry_path: Path | None = None
    wikis: list[WikiTarget] = field(default_factory=list)
    shared: list[SharedTarget] = field(default_factory=list)
    user_mcp: list[McpRemoval] = field(default_factory=list)
    #: Skill user-global (`~/.agents/skills/`) — cùng nhóm user-scope với user_mcp.
    user_skills: list[SkillsRemoval] = field(default_factory=list)
    #: registry entry trỏ tới folder không còn trên đĩa (chỉ báo, không dọn được).
    missing: list[str] = field(default_factory=list)

    def has_anything(self) -> bool:
        return bool(self.base_exists or self.wikis or self.shared
                    or self.user_mcp or self.user_skills
                    or self.registry_path is not None)

    def counts(self) -> dict[str, int]:
        """Tổng hợp để hiển thị + quyết định có gì để làm hay không."""
        wikis = list(self.wikis)
        n_mcp = sum(len(m.names) for w in wikis for m in w.mcp)
        n_mcp += sum(len(m.names) for s in self.shared for m in s.mcp)
        n_mcp += sum(len(m.names) for m in self.user_mcp)
        n_skill = sum(len(k.names) for w in wikis for k in w.skills)
        n_skill += sum(len(k.names) for s in self.shared for k in s.skills)
        n_links = sum(len(k.links) for w in wikis for k in w.skills)
        n_links += sum(len(k.links) for s in self.shared for k in s.skills)
        n_skill += sum(len(k.names) for k in self.user_skills)
        n_links += sum(len(k.links) for k in self.user_skills)
        n_research = (sum(len(s.research_files) for s in self.shared)
                      + sum(len(w.research_files) for w in wikis))
        n_state = (sum(1 for w in wikis if w.state_dir is not None)
                   + sum(1 for s in self.shared if s.state_dir is not None))
        return {
            "mcp_entries": n_mcp,
            "mcp_files": (sum(len(w.mcp) for w in wikis)
                          + sum(len(s.mcp) for s in self.shared)
                          + len(self.user_mcp)),
            "skills": n_skill,
            "links": n_links,
            "research": n_research,
            "state_dirs": n_state,
            "wiki_targets": len(wikis),
            "shared_targets": len(self.shared),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Build plan (read-only)
# ─────────────────────────────────────────────────────────────────────────────


def _ancestor_roots(wiki_dir: Path, home: Path, base: Path,
                     wiki_dirs: set[Path]) -> list[Path]:
    """Tầng cha của một project wiki, nơi repo-root footprint có thể nằm.

    Loại trừ có chủ đích:
      - một wiki khác (`wiki_dirs`) — footprint của nó do đích thân nó dọn;
      - base dir và tổ tiên của nó — base bị xoá toàn bộ ở bước cuối, đừng dọn lộn;
      - `$HOME` trở lên — đó là lãnh thổ user-scope, chỉ được đụng khi
        `include_user` BẬT (kẻo `--no-user-config` vẫn làm bẩn config cá nhân).
    """
    out: list[Path] = []
    for root in list(wiki_dir.parents)[:ROOT_SEARCH_DEPTH]:
        if root in wiki_dirs:
            continue
        if root == base or base in root.parents:
            continue
        if root == home or root in home.parents:
            continue
        out.append(root)
    return out


def _mcp_files_for_root(root: Path) -> list[tuple[str, Path]]:
    """(client, path) cho mọi file config MCP project-scope đang tồn tại dưới `root`.

    Chỉ ghi nhận một lần mỗi path: `claude` và `commandcode` cùng dùng `.mcp.json`
    với cùng schema (`mcpServers`) → kẻo đếm trùng và gỡ file hai lần.
    """
    out: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for client in supported_clients():
        p = get_project_mcp_path(client, root)
        if p is None or not p.exists() or p in seen:
            continue
        seen.add(p)
        out.append((client, p))
    return out


def _scan_mcp(root: Path, scope: str) -> list[McpRemoval]:
    hits: list[McpRemoval] = []
    for client, cfg in _mcp_files_for_root(root):
        names = find_our_mcp_entries(client, cfg)
        if names:
            hits.append(McpRemoval(client=client, path=cfg, names=names, scope=scope))
    return hits


def _scan_skills(root: Path) -> SkillsRemoval | None:
    from llm_wiki_base._skills import find_our_skills

    names, links = find_our_skills(root)
    if not names and not links:
        return None
    return SkillsRemoval(root=root, names=names, links=links)


def _scan_research(root: Path) -> list[Path]:
    from llm_wiki_base.init_project import has_research_block

    return [root / rel for rel in RESEARCH_RELS if has_research_block(root / rel)]


def build_plan(extra_roots: list[Path] | None = None,
               include_user: bool = True) -> Plan:
    """Quét toàn bộ footprint của tool, trả `Plan` — KHÔNG sửa gì xuống đĩa.

    `extra_roots`: thêm wiki không có trong registry (khởi tạo bằng `--no-register`)
    hoặc folder tự tay dọn. Chúng được coi là personal wiki dir.
    """
    base = get_base_dir()
    reg = get_registry_path()
    plan = Plan(base_dir=base, base_exists=base.is_dir(),
                registry_path=reg if reg.is_file() else None)

    entries = list(list_wikis())
    for extra in (extra_roots or []):
        resolved = Path(extra).expanduser().resolve()
        entries.append({"name": resolved.name, "path": str(resolved),
                        "type": "personal"})

    wiki_dirs: dict[Path, str] = {}
    for entry in entries:
        p = Path(str(entry.get("path", ""))).expanduser()
        if p.is_dir():
            wiki_dirs[p.resolve()] = str(entry.get("name", p.name))

    # So với path đã resolve của wiki: `$HOME` và mọi thứ phía trên nó là lãnh thổ
    # user-scope, chỉ đụng tới khi `include_user` BẬT.
    home = Path.home().resolve()
    shared: dict[Path, SharedTarget] = {}
    #: Path wiki đã xử lý — `--path` trùng một entry trong registry không được
    #: khiến footprint hiện ra (và bị tính) hai lần.
    processed: set[Path] = set()

    for entry in entries:
        raw_path = str(entry.get("path", ""))
        wiki_dir = Path(raw_path).expanduser()
        if not wiki_dir.is_dir():
            if not raw_path:
                continue
            name = str(entry.get("name", wiki_dir.name))
            if name not in plan.missing:
                plan.missing.append(name)
            continue
        resolved = wiki_dir.resolve()
        if resolved in processed:
            continue
        processed.add(resolved)
        wiki_type = str(entry.get("type", "personal"))

        target = WikiTarget(name=str(entry.get("name", wiki_dir.name)), path=resolved)
        # MCP file nằm NGAY TRONG wiki dir (personal wiki init) → thuộc về wiki này.
        target.mcp = _scan_mcp(resolved, "project")
        own_skills = _scan_skills(resolved)
        if own_skills:
            target.skills.append(own_skills)
        # `--path <repo>` được hiểu là personal dir → research block của repo nằm
        # ngay tại đó cũng phải bị gỡ.
        target.research_files = _scan_research(resolved)
        state = resolved / STATE_DIR
        if state.is_dir():
            target.state_dir = state
        if not target.is_empty():
            plan.wikis.append(target)

        if wiki_type != "project":
            continue
        # Project wiki: MCP + codebase skill + research block nằm ở repo root.
        for root in _ancestor_roots(resolved, home, base, set(wiki_dirs)):
            st = shared.get(root)
            if st is None:
                st = SharedTarget(path=root)
                shared[root] = st
            owner = str(entry.get("name", resolved.name))
            if owner not in st.wikis:
                st.wikis.append(owner)

    # Dọn các shared root MỘT LẦN — scan sau khi đã biết đủ danh sách wiki để
    # root nào là wiki thì loại ra (`wiki_dirs` ở trên).
    for root, st in shared.items():
        st.mcp = _scan_mcp(root, "project")
        sk = _scan_skills(root)
        if sk:
            st.skills.append(sk)
        st.research_files = _scan_research(root)
        state = root / STATE_DIR
        if state.is_dir():
            # `upgrade` stamp VERSION + backups ở repo root cho codebase skill.
            st.state_dir = state
        if not st.is_empty():
            plan.shared.append(st)

    if include_user:
        # User scope = mọi thứ nằm thẳng dưới $HOME: config MCP cá nhân của từng
        # client (`~/.claude/…`, `~/.commandcode/mcp.json`) + skill toàn cục
        # `~/.agents/skills/` (Command Code đọc trực tiếp chỗ này).
        for client in supported_clients():
            try:
                cfg = get_mcp_config_path(client)
            except ValueError:
                continue
            names = find_our_mcp_entries(client, cfg)
            if names:
                plan.user_mcp.append(McpRemoval(client=client, path=cfg,
                                                names=names, scope="user"))
        user_skills = _scan_skills(home)
        if user_skills:
            plan.user_skills.append(user_skills)
    return plan


# ─────────────────────────────────────────────────────────────────────────────
# Apply plan (mutating)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Summary:
    mcp_entries: int = 0
    skill_dirs: int = 0
    links: int = 0
    research_blocks: int = 0
    state_dirs: int = 0
    base_dir_removed: bool = False
    skipped_files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def changed_anything(self) -> bool:
        return bool(self.mcp_entries or self.skill_dirs or self.links
                    or self.research_blocks or self.state_dirs
                    or self.base_dir_removed)


def _remove_mcp(items: list[McpRemoval], s: Summary) -> None:
    for m in items:
        _names, note = remove_our_mcp_entries(m.client, m.path)
        if note == "removed":
            s.mcp_entries += len(m.names)
        elif note == "unreadable":
            s.warnings.append(f"{m.path}: not valid JSON — left untouched, "
                              "remove the llm-wiki-base entry by hand")
        elif note == "absent":
            s.skipped_files.append(m.path)


def _remove_skills(items: list[SkillsRemoval], s: Summary) -> None:
    from llm_wiki_base._skills import uninstall_skills

    for sk in items:
        removed = uninstall_skills(sk.root)
        s.skill_dirs += len(removed)
        s.links += sum(1 for link in sk.links if not link.exists())


def _remove_research(roots: list[Path], s: Summary) -> None:
    from llm_wiki_base.init_project import strip_research_block

    for root in roots:
        s.research_blocks += len(strip_research_block(root))


def _remove_state(state: Path, s: Summary) -> None:
    """Xoá một state dir `.llm-wiki-base/` (VERSION + tool backups) — không phải data wiki."""
    if not state.is_dir():
        return
    shutil.rmtree(state, ignore_errors=True)
    if state.exists():
        s.warnings.append(f"could not remove {state}")
    else:
        s.state_dirs += 1


#: Thứ mà `setup tools` để lại trong base dir — dùng để xác nhận một path đúng là
#: runtime của llm-wiki-base trước khi nỡ `rmtree` nó.
_BASE_MARKERS = ("tools", "rag", "scripts", ".venv", "registry.toml")


def looks_like_base_dir(path: Path) -> bool:
    """`path` có phải global runtime của llm-wiki-base? Chốt chặn cho `rmtree`.

    Env `LLM_WIKI_BASE_DIR` do user đặt — nếu nó trỏ sai (vd thẳng vào $HOME) thì
    uninstall không được phép xoá sạch theo. Chấp nhận khi: tên là `.llm-wiki-base`
    (layout mặc định) HOẶC chứa ít nhất một marker runtime.
    """
    try:
        if path == Path.home() or path.parent == path:
            return False
        if path.name == ".llm-wiki-base":
            return True
        return any((path / m).exists() for m in _BASE_MARKERS)
    except OSError:
        return False


def apply_plan(plan: Plan, *, keep_base: bool = False) -> Summary:
    """Thực thi plan: MCP → skills → research block → state dir → registry → base dir.

    Thứ tự có chủ đích: mọi thông tin cần đọc (registry) đã nằm trong plan từ
    `build_plan`, nên global base — thứ chứa registry.toml — bị xoá CUỐI cùng.
    Mỗi bước idempotent: mục tiêu đã biến mất thì bỏ qua, chạy lại lệnh không sao.
    """
    s = Summary()

    for wiki in plan.wikis:
        _remove_mcp(wiki.mcp, s)
        _remove_skills(wiki.skills, s)
        if wiki.research_files:
            _remove_research([wiki.path], s)
    for st in plan.shared:
        _remove_mcp(st.mcp, s)
        _remove_skills(st.skills, s)
        if st.research_files:
            _remove_research([st.path], s)
        if st.state_dir is not None:
            _remove_state(st.state_dir, s)
    _remove_mcp(plan.user_mcp, s)
    _remove_skills(plan.user_skills, s)

    for wiki in plan.wikis:
        if wiki.state_dir is not None:
            _remove_state(wiki.state_dir, s)

    if not keep_base and plan.base_exists:
        if not looks_like_base_dir(plan.base_dir):
            # Chốt an toàn: env `LLM_WIKI_BASE_DIR` trỏ sai chỗ (vd chỉ thẳng $HOME)
            # thì không được `rmtree -rf` theo. Báo để user tự lo.
            s.warnings.append(
                f"refusing to delete {plan.base_dir}: it has none of the llm-wiki-base "
                "runtime markers (tools/ rag/ scripts/ .venv/) — remove it by hand")
        else:
            shutil.rmtree(plan.base_dir, ignore_errors=True)
            if plan.base_dir.exists():
                s.warnings.append(f"could not remove {plan.base_dir} — delete it manually")
            else:
                s.base_dir_removed = True

    # registry.toml có thể nằm NGOÀI base (env `LLM_WIKI_BASE_REGISTRY`) → base đã
    # xoá vẫn còn sót file, dọn riêng khi nó vẫn tồn tại.
    if plan.registry_path is not None and plan.registry_path.exists():
        try:
            plan.registry_path.unlink()
        except OSError:
            s.warnings.append(f"could not remove {plan.registry_path} — delete it manually")
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Reporting (dùng cho cả dry-run lẫn preview trước confirm)
# ─────────────────────────────────────────────────────────────────────────────


#: Rộng cột nhãn của các dòng chi tiết (indented under a target).
_LABEL_W = 10


def _detail(label: str, text: str) -> str:
    return f"    {label:<{_LABEL_W}} {text}"


def plan_facts(plan: Plan) -> list[str]:
    """Các dòng sự thật của plan: những gì SẼ bị xoá. Quiet-mode friendly.

    Không chứa markup Rich (đường dẫn do user đặt có thể có `[...]`) — caller in
    với `markup=False`.
    """
    rows: list[str] = []
    if plan.base_exists:
        rows.append(f"global runtime  {plan.base_dir}")
    if plan.registry_path is not None:
        rows.append(f"registry file   {plan.registry_path}")
    for wiki in plan.wikis:
        rows.append(f"wiki '{wiki.name}'  {wiki.path}")
        rows.extend(_mcp_lines(wiki.mcp))
        rows.extend(_skill_lines(wiki.skills))
        for f in wiki.research_files:
            rows.append(_detail("research", str(f)))
        if wiki.state_dir is not None:
            rows.append(_detail("state", str(wiki.state_dir)))
    for st in plan.shared:
        owners = ", ".join(st.wikis) or "?"
        rows.append(f"shared root  {st.path}  (wikis: {owners})")
        rows.extend(_mcp_lines(st.mcp))
        rows.extend(_skill_lines(st.skills))
        for f in st.research_files:
            rows.append(_detail("research", str(f)))
        if st.state_dir is not None:
            rows.append(_detail("state", str(st.state_dir)))
    if plan.user_mcp or plan.user_skills:
        rows.append("user-scope footprint")
        rows.extend(_mcp_lines(plan.user_mcp))
        rows.extend(_skill_lines(plan.user_skills))
    for name in plan.missing:
        rows.append(f"skip            wiki '{name}': registered path no longer exists")
    if not rows:
        rows.append("nothing to remove — llm-wiki-base leaves no footprint here")
    return rows


def _mcp_lines(items: list[McpRemoval]) -> list[str]:
    # Nhãn client để trong `()` chứ không `[]`: Rich ăn `[...]` như style tag.
    return [_detail("mcp", f"({m.client}) {m.path} → {', '.join(m.names)}")
            for m in items]


def _skill_lines(items: list[SkillsRemoval]) -> list[str]:
    out: list[str] = []
    for sk in items:
        detail = ", ".join(sk.names) if sk.names else "(client links only)"
        out.append(_detail("skills", f"{sk.root / AGENTS_SKILLS} → {detail}"))
        if sk.links:
            out.append(_detail("links", str(len(sk.links))))
    return out
