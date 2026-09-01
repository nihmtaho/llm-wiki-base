"""llm-wiki-base-mcp — Centralized MCP bridge cho nhiều wiki.

MỘT MCP server duy nhất (cấu hình 1 entry trong Claude/OpenCode/Zed) phục vụ
tất cả wikis đã đăng ký trong `<base_dir>/registry.toml` (TOML).

Targeting:
- `wiki` parameter (tên wiki trong registry) → làm việc với wiki cụ thể.
- `wiki=""` (rỗng) → tự động search/read across ALL registered wikis (cross-scope,
  bao gồm cả personal wiki).

Safety: MCP KHÔNG ingest. Chỉ được phép:
- SEARCH / READ (wiki_search, semantic_search, wiki_read, wiki_list, wiki_lint)
- CONTRIBUTE vào wiki do human chỉ định (wiki_submit → raw/inbox/, wiki_propose_edit → .proposals/)

Ingest lên wiki/ là maintainer-only (CLI / skill), không qua MCP.

Transport: stdio. Logging → stderr (stdout dành cho JSON-RPC).
"""
import datetime
import json
import logging
import math
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# tools/ dir (where this file is copied to) chứa db.py, search.py, lint.py, embed.py, paths.py
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import db
import lint as lintmod
import search
from embed import EmbedProvider

# ── Registry ─────────────────────────────────────────────────────────────────
_BASE_DIR = os.environ.get("LLM_WIKI_BASE_DIR") or os.path.expanduser("~/.llm-wiki-base")
_REGISTRY_PATH = Path(_BASE_DIR) / "registry.toml"

try:
    import tomllib  # py3.11+
except ImportError:
    import tomli as tomllib  # type: ignore

# ── Logging → stderr only ────────────────────────────────────────────────────
logging.basicConfig(
    level=os.environ.get("WIKI_MCP_LOG", "INFO"),
    format="%(asctime)s %(levelname)s llm-wiki-base-mcp %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("llm-wiki-base-mcp")

mcp = FastMCP("llm-wiki-base-mcp")
SERVER_NAME = "llm-wiki-base-mcp"

# Shared embed provider (lazy-load model once)
_embed_provider: EmbedProvider | None = None


def _provider() -> EmbedProvider:
    global _embed_provider
    if _embed_provider is None:
        _embed_provider = EmbedProvider()
    return _embed_provider


# ── Registry helpers ─────────────────────────────────────────────────────────


def _load_registry() -> list[dict]:
    """Load wiki list từ registry.toml. Trả [] nếu file không tồn tại/rỗng."""
    if not _REGISTRY_PATH.exists():
        return []
    try:
        with _REGISTRY_PATH.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        log.exception("registry.toml corrupt — treating as empty")
        return []
    return data.get("wikis", [])


def _wiki_entry(name: str) -> dict | None:
    """Tìm wiki entry theo name trong registry."""
    return next((w for w in _load_registry() if w.get("name") == name), None)


def _set_wiki_ctx(wiki_name: str) -> tuple[str, Path]:
    """Set db module globals cho 1 wiki cụ thể. Trả (wiki_root, wiki_dir).

    Centralized MCP server gọi hàm này trước mỗi tool call để chuyển context.
    """
    entry = _wiki_entry(wiki_name)
    if entry is None:
        raise ValueError(
            f"wiki '{wiki_name}' không có trong registry. "
            f"Chạy `llm-wiki wiki list` để xem wikis đã đăng ký."
        )
    root = str(Path(entry["path"]).resolve())
    wiki_dir = Path(root) / "wiki"
    db_path = str(wiki_dir / ".wiki.db")
    db.WIKI_ROOT = root
    db.DB_PATH = db_path
    os.environ["WIKI_DB"] = db_path
    os.environ["WIKI_ROOT"] = root
    os.environ["WIKI_DIR"] = str(wiki_dir)
    os.environ["WIKI_PROPOSALS"] = str(wiki_dir / ".proposals")
    os.environ["RAW_INBOX"] = str(Path(root) / "raw" / "inbox")
    os.environ["RAW_DIR"] = str(Path(root) / "raw")
    os.environ["RAG_INDEX_DIR"] = str(Path(root) / "rag" / ".rag_index")
    return root, wiki_dir


def _resolve_in_wiki(wiki: str, rel_path: str) -> Path | None:
    """Resolve path dưới wiki root, chặn traversal. Trả None nếu ngoài scope."""
    entry = _wiki_entry(wiki)
    if not entry:
        return None
    root = Path(entry["path"]).resolve()
    p = (root / rel_path).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def _resolve_any(rel_path: str) -> list[tuple[str, Path]]:
    """Resolve path across ALL wikis. Trả list (wiki_name, path) cho file tồn tại."""
    results: list[tuple[str, Path]] = []
    for w in _load_registry():
        root = Path(w["path"]).resolve()
        p = (root / rel_path).resolve()
        try:
            p.relative_to(root)
            if p.exists():
                results.append((w["name"], p))
        except ValueError:
            continue
    return results


def _wiki_db_path(wiki: str) -> str | None:
    """SQLite DB path cho 1 wiki."""
    entry = _wiki_entry(wiki)
    if not entry:
        return None
    root = Path(entry["path"]).resolve()
    return str(root / "wiki" / ".wiki.db")


def _slug(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9 _-]", "", title).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s or "untitled"


def _err(msg: str, **extra: Any) -> dict:
    d: dict = {"error": msg}
    d.update(extra)
    return d


# ── Resources (read-only) ─────────────────────────────────────────────────────


@mcp.resource("registry://wikis")
def registry_list() -> str:
    """Danh sách tất cả wikis trong registry."""
    wikis = _load_registry()
    if not wikis:
        return "(registry rỗng — chạy `llm-wiki init` để đăng ký wiki)"
    lines = []
    for w in wikis:
        lines.append(f"- **{w['name']}** ({w.get('type', '?')}) → `{w['path']}`")
    return "\n".join(lines)


@mcp.resource("wiki://{name}/index")
def wiki_index(name: str) -> str:
    """Wiki top-level index của 1 wiki cụ thể."""
    full = _resolve_in_wiki(name, "wiki/index.md")
    if full is None:
        return f"(wiki '{name}' không có trong registry)"
    if not full.exists():
        return "(wiki/index.md chưa tạo)"
    return full.read_text(encoding="utf-8")


@mcp.resource("wiki://{name}/log")
def wiki_log(name: str) -> str:
    """Wiki log (append-only) của 1 wiki cụ thể."""
    full = _resolve_in_wiki(name, "wiki/log.md")
    if full is None:
        return f"(wiki '{name}' không có trong registry)"
    if not full.exists():
        return "(wiki/log.md chưa tạo)"
    return full.read_text(encoding="utf-8")


# ── Search tools ─────────────────────────────────────────────────────────────


@mcp.tool()
def wiki_search(query: str, top_k: int = 8, wiki: str = "") -> list:
    """Hybrid search (BM25 + vector cosine) trên wiki(ies).

    Args:
        query: câu hỏi/từ khóa tìm kiếm.
        top_k: số kết quả tối đa (mỗi wiki).
        wiki: tên wiki cụ thể trong registry. Rỗng = search ALL wikis.

    Trả về list[{path, title, domain, kind, score, snippet, wiki}] sắp xếp theo score.
    Kết quả được gán `wiki` = tên wiki nguồn để phân biệt.
    """
    if wiki:
        if not _wiki_entry(wiki):
            return [_err(f"wiki '{wiki}' không có trong registry")]
        wikis_to_search = [{"name": wiki}]
    else:
        wikis_to_search = _load_registry()
        if not wikis_to_search:
            return [_err("registry rỗng — chạy `llm-wiki init` để đăng ký wiki")]

    all_results: list = []
    provider = _provider()
    for w in wikis_to_search:
        try:
            root, _ = _set_wiki_ctx(w["name"])
            conn = db.get_conn(db.DB_PATH)
            db.init_db(conn)
            results = search.hybrid_search(conn, query, top_k=top_k, provider=provider)
            for r in results:
                r["wiki"] = w["name"]
            conn.close()
            all_results.extend(results)
        except Exception as e:
            log.exception("wiki_search failed for %s", w.get("name"))
            all_results.append(_err(f"search error in '{w.get('name')}': {e}", wiki=w.get("name")))

    all_results.sort(
        key=lambda x: x.get("score", 0) if isinstance(x.get("score", 0), (int, float)) else 0,
        reverse=True,
    )
    return all_results[:top_k]


@mcp.tool()
def semantic_search(query: str, top_k: int = 6, wiki: str = "") -> list:
    """Semantic chunk-level search (cần `rag/index.py` build trước).

    Args:
        query: câu hỏi.
        top_k: số kết quả.
        wiki: tên wiki. Rỗng = search ALL wikis (mỗi wiki cần có .rag_index).

    Trả về list[{path, chunk, score, snippet, wiki}]. Wiki chưa build RAG index
    sẽ bị bỏ qua (không lỗi).
    """
    try:
        import numpy as np
    except ImportError:
        return [_err("numpy chưa cài trong base venv")]

    if wiki:
        if not _wiki_entry(wiki):
            return [_err(f"wiki '{wiki}' không có trong registry")]
        wikis_to_search = [{"name": wiki}]
    else:
        wikis_to_search = _load_registry()
        if not wikis_to_search:
            return [_err("registry rỗng — chạy `llm-wiki init` để đăng ký wiki")]

    provider = _provider()
    q_vec = None
    all_results: list = []

    for w in wikis_to_search:
        try:
            root, _ = _set_wiki_ctx(w["name"])
            index_dir = Path(root) / "rag" / ".rag_index"
            vectors_file = index_dir / "vectors.npy"
            chunks_file = index_dir / "chunks.json"
            if not vectors_file.exists() or not chunks_file.exists():
                continue  # wiki chưa build RAG index — bỏ qua
            arr = np.load(str(vectors_file))
            with open(chunks_file, encoding="utf-8") as f:
                meta = json.load(f)
            if q_vec is None:
                q_vec = np.array(provider.embed([query])[0], dtype="float32")
                q_vec /= np.linalg.norm(q_vec) + 1e-9
            norms = np.linalg.norm(arr, axis=1) + 1e-9
            sims = (arr / norms[:, None]) @ q_vec
            idx = sims.argsort()[::-1][:top_k]
            for i in idx:
                all_results.append({
                    "path": meta[i]["path"],
                    "chunk": meta[i]["chunk"],
                    "score": round(float(sims[i]), 4),
                    "snippet": meta[i]["text"][:300],
                    "wiki": w["name"],
                })
        except Exception as e:
            log.warning("semantic_search unavailable for %s: %s", w.get("name"), e)

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]


@mcp.tool()
def wiki_read(path: str, wiki: str = "") -> dict:
    """Đọc nguyên nội dung 1 file (wiki page hoặc raw source).

    Args:
        path: đường dẫn relative, ví dụ 'wiki/tech/index.md'.
        wiki: tên wiki cụ thể. Rỗng = tìm trong ALL wikis (lỗi nếu trùng ở nhiều wiki).
    """
    if wiki:
        if not _wiki_entry(wiki):
            return _err(f"wiki '{wiki}' không có trong registry")
        full = _resolve_in_wiki(wiki, path)
        if full is None:
            return _err(f"path ngoài wiki root của '{wiki}': {path}")
        if not full.exists():
            return _err(f"not found: {path} (wiki: {wiki})")
        return {"path": path, "wiki": wiki, "content": full.read_text(encoding="utf-8")}

    # Cross-wiki: tìm path trong tất cả wikis
    results = _resolve_any(path)
    if not results:
        return _err(f"not found in any wiki: {path}")
    if len(results) > 1:
        names = [w for w, _ in results]
        return _err(f"path '{path}' tồn tại ở nhiều wiki: {names}. Chỉ định `wiki=`")
    wname, full = results[0]
    return {"path": path, "wiki": wname, "content": full.read_text(encoding="utf-8")}


@mcp.tool()
def wiki_list(domain: str = "", kind: str = "", category: str = "", wiki: str = "") -> list:
    """Liệt kê wiki pages, filter theo domain/kind.

    Args:
        domain: filter theo domain (top-level folder).
        kind: filter theo semantic role (entity|concept|source|task).
        category: LEGACY alias cho domain.
        wiki: tên wiki cụ thể. Rỗng = list từ ALL wikis.
    """
    dom = domain or category or None

    if wiki:
        if not _wiki_entry(wiki):
            return [_err(f"wiki '{wiki}' không có trong registry")]
        wikis_to_search = [{"name": wiki}]
    else:
        wikis_to_search = _load_registry()
        if not wikis_to_search:
            return [_err("registry rỗng — chạy `llm-wiki init` để đăng ký wiki")]

    results: list = []
    for w in wikis_to_search:
        try:
            _set_wiki_ctx(w["name"])
            conn = db.get_conn(db.DB_PATH)
            db.init_db(conn)
            pages = db.list_pages(conn, domain=dom, kind=kind or None)
            conn.close()
            for p in pages:
                p["wiki"] = w["name"]
                results.append(p)
        except Exception as e:
            results.append({"error": str(e), "wiki": w["name"]})
    return results


@mcp.tool()
def list_raw_source(subdir: str = "inbox", wiki: str = "") -> list:
    """Liệt kê nguồn thô trong raw/<subdir>/.

    Args:
        subdir: thư mục con trong raw/ (mặc định 'inbox').
        wiki: tên wiki. Rỗng = list từ ALL wikis.
    """
    if wiki:
        if not _wiki_entry(wiki):
            return [_err(f"wiki '{wiki}' không có trong registry")]
        wikis_to_search = [{"name": wiki}]
    else:
        wikis_to_search = _load_registry()
        if not wikis_to_search:
            return [_err("registry rỗng")]

    results: list = []
    for w in wikis_to_search:
        root = Path(w["path"]).resolve()
        d = root / "raw" / subdir
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                results.append({"name": f.name, "wiki": w["name"], "subdir": subdir})

    # Flat list (just names) nếu target single wiki
    if wiki:
        results = [{"name": r["name"], "subdir": r["subdir"]} for r in results]
    return results


@mcp.tool()
def read_raw_source(name: str, subdir: str = "inbox", wiki: str = "") -> dict:
    """Đọc nguồn gốc từ raw/<subdir>/<name>.

    Args:
        name: filename, ví dụ '2026-08-foo.md'.
        subdir: thư mục con trong raw/ (mặc định 'inbox').
        wiki: tên wiki. Rỗng = tìm trong ALL wikis.
    """
    rel = str(Path("raw") / subdir / name)
    if wiki:
        if not _wiki_entry(wiki):
            return _err(f"wiki '{wiki}' không có trong registry")
        full = _resolve_in_wiki(wiki, rel)
        if full is None:
            return _err(f"path ngoài wiki root của '{wiki}': {rel}")
        if not full.exists():
            return _err(f"not found: raw/{subdir}/{name} (wiki: {wiki})")
        return {"path": f"raw/{subdir}/{name}", "wiki": wiki, "content": full.read_text(encoding="utf-8")}

    results = _resolve_any(rel)
    if not results:
        return _err(f"not found in any wiki: raw/{subdir}/{name}")
    if len(results) > 1:
        names = [w for w, _ in results]
        return _err(f"raw/{subdir}/{name} tồn tại ở nhiều wiki: {names}. Chỉ định `wiki=`")
    wname, full = results[0]
    return {"path": f"raw/{subdir}/{name}", "wiki": wname, "content": full.read_text(encoding="utf-8")}


# ── Write tools (controlled — NEVER ingest) ───────────────────────────────────


@mcp.tool()
def wiki_submit(
    title: str,
    content: str,
    wiki: str,
    domain: str = "",
    source: str = "",
    category: str = "",
) -> dict:
    """NẠP NGỮ CẢNH DUY NHẤT ĐƯỢC PHÉP: ghi vào raw/inbox/ của wiki do human chỉ định.

    MCP KHÔNG ingest. Maintainer (CLI/skill) sẽ ingest từ inbox → wiki/ sau khi
    human duyệt. Tool này chỉ staging, không lên wiki/.

    Args:
        title: tiêu đề — dùng làm slug filename.
        content: nội dung markdown.
        wiki: **bắt buộc** — tên wiki để nạp (human phải chỉ định).
        domain: gợi ý domain (top-level folder).
        source: URL/citation gốc.
        category: LEGACY alias cho domain.
    """
    entry = _wiki_entry(wiki)
    if entry is None:
        return _err(f"wiki '{wiki}' không có trong registry. Chạy `llm-wiki wiki list`")
    root, _ = _set_wiki_ctx(wiki)
    inbox = Path(root) / "raw" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    fname = f"{_slug(title)}.md"
    full = inbox / fname
    if full.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        full = inbox / f"{_slug(title)}-{stamp}.md"
    dom = domain or category or ""
    fm = (
        f"---\n"
        f"title: {title}\n"
        f"domain: {dom}\n"
        f"source: {source}\n"
        f"submitted: {datetime.datetime.now().isoformat(timespec='seconds')}\n"
        f"status: inbox\n"
        f"---\n\n"
    )
    full.write_text(fm + content + "\n", encoding="utf-8")
    rel = str(full.relative_to(root))
    log.info("submitted to inbox: %s (wiki=%s)", rel, wiki)
    return {
        "submitted": rel,
        "wiki": wiki,
        "domain": dom,
        "note": "Đã nạp vào raw/inbox. Chờ maintainer ingest lên wiki (MCP không ingest).",
    }


@mcp.tool()
def wiki_propose_edit(path: str, content: str, wiki: str) -> dict:
    """ĐỀ XUẤT sửa wiki (staging). Ghi vào wiki/.proposals/, KHÔNG sửa wiki trực tiếp.

    Args:
        path: path wiki page mục tiêu, ví dụ 'wiki/tech/foo.md'.
        content: nội dung markdown mới đề xuất.
        wiki: **bắt buộc** — tên wiki để đề xuất (human phải chỉ định).
    """
    entry = _wiki_entry(wiki)
    if entry is None:
        return _err(f"wiki '{wiki}' không có trong registry. Chạy `llm-wiki wiki list`")
    root, _ = _set_wiki_ctx(wiki)
    proposals_dir = Path(root) / "wiki" / ".proposals"
    if _resolve_in_wiki(wiki, path) is None:
        return _err(f"target path ngoài wiki root của '{wiki}': {path}")
    proposals_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(path))
    prop_path = proposals_dir / f"{stamp}__{safe}"
    prop_path.write_text(content, encoding="utf-8")
    log.info("proposal staged: %s → %s (wiki=%s)", prop_path.relative_to(root), path, wiki)
    return {
        "staged": str(prop_path.relative_to(root)),
        "target": path,
        "wiki": wiki,
        "note": "Human review proposal trước khi apply vào wiki.",
    }


@mcp.tool()
def wiki_lint(wiki: str = "") -> dict:
    """Health-check wiki: orphan, broken [[wikilinks]], missing file.

    Args:
        wiki: tên wiki cụ thể. Rỗng = lint ALL wikis (trả dict theo tên wiki).
    """
    if wiki:
        if not _wiki_entry(wiki):
            return _err(f"wiki '{wiki}' không có trong registry")
        _set_wiki_ctx(wiki)
        conn = db.get_conn(db.DB_PATH)
        db.init_db(conn)
        result = lintmod.lint(conn, wiki_root=db.WIKI_ROOT)
        conn.close()
        return result

    wikis = _load_registry()
    if not wikis:
        return _err("registry rỗng")
    out: dict[str, Any] = {}
    for w in wikis:
        try:
            root, _ = _set_wiki_ctx(w["name"])
            conn = db.get_conn(db.DB_PATH)
            db.init_db(conn)
            out[w["name"]] = lintmod.lint(conn, wiki_root=root)
            conn.close()
        except Exception as e:
            out[w["name"]] = _err(str(e))
    return out


if __name__ == "__main__":
    log.info("starting %s (stdio)", SERVER_NAME)
    try:
        mcp.run()
    except KeyboardInterrupt:
        log.info("interrupted")
        sys.exit(0)
