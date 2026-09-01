"""llm-wiki-mcp — MCP bridge for AI clients to read/search the wiki.

MCP = cầu nối cho các AI khác kết nối tới wiki. Không viết thẳng wiki/.
- Đọc / tìm kiếm: wiki_search, semantic_search, wiki_read, wiki_list,
                   list_raw_source, read_raw_source.
- Nạp context (WRITE duy nhất, có kiểm soát): wiki_submit → raw/inbox/.
- Đề xuất (staging, an toàn): wiki_propose_edit → wiki/.proposals/.
- Index / ingest lên wiki là việc maintainer (CLI / skill), không qua MCP.

Transport: stdio. Logging đi stderr để không phá JSON-RPC stream.
"""
import datetime
import importlib.util
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

import db
import lint as lintmod
import search
from embed import EmbedProvider
from paths import WIKI_ROOT, WIKI_INDEX_FILE, WIKI_LOG_FILE, WIKI_PROPOSALS, RAW_INBOX, RAG_DIR, RAW_DIR

WIKI_ROOT = str(WIKI_ROOT)
PROPOSALS_DIR = Path(WIKI_PROPOSALS)
RAW_INBOX = Path(RAW_INBOX)
RAW_DIR = Path(RAW_DIR)
WIKI_DIR = Path(WIKI_ROOT) / "wiki"

if str(RAG_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_DIR))
# Per-wiki RAG_DIR chỉ chứa .rag_index/ data, KHÔNG có code.
# Load rag.search từ global base (LLM_WIKI_BASE_DIR hoặc default).
_BASE_DIR = os.environ.get("LLM_WIKI_BASE_DIR") or os.path.expanduser("~/.llm-wiki-base")
_GLOBAL_RAG = Path(_BASE_DIR) / "rag"
_spec = importlib.util.spec_from_file_location(
    "rag_search_mod", _GLOBAL_RAG / "search.py"
)
rag_search = importlib.util.module_from_spec(_spec)
sys.modules["rag_search_mod"] = rag_search
_spec.loader.exec_module(rag_search)

# Logging → stderr only (stdio transport). stdout reserved for JSON-RPC.
logging.basicConfig(
    level=os.environ.get("WIKI_MCP_LOG", "INFO"),
    format="%(asctime)s %(levelname)s llm-wiki-mcp %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("llm-wiki-mcp")

mcp = FastMCP("llm-wiki-mcp")


def _conn():
    c = db.get_conn()
    db.init_db(c)
    return c


def _provider():
    return EmbedProvider()


def _slug(title: str) -> str:
    """Slug ASCII an toàn cho filename — dùng từ scripts/common.py semantics."""
    s = re.sub(r"[^a-zA-Z0-9 _-]", "", title).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s or "untitled"


def _resolve(rel_path: str) -> Path | None:
    """Resolve path dưới WIKI_ROOT, chặn traversal. Trả None nếu ngoài phạm vi."""
    p = (Path(WIKI_ROOT) / rel_path).resolve()
    root = Path(WIKI_ROOT).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        return None
    return p


def _err(msg: str, **extra: Any) -> dict:
    """Response lỗi đồng nhất cho AI client retry thông minh."""
    d = {"error": msg}
    d.update(extra)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Resources — read-only, model có thể attach tự động khi cần context.
# ─────────────────────────────────────────────────────────────────────────────


@mcp.resource("wiki://index")
def wiki_index() -> str:
    """Wiki top-level index — liệt kê tất cả domain (top-level folders, không cố định 3)."""
    p = Path(WIKI_INDEX_FILE)
    return p.read_text(encoding="utf-8") if p.exists() else "(wiki/index.md chưa tạo)"


@mcp.resource("wiki://log")
def wiki_log() -> str:
    """Wiki log append-only — lịch sử ingest."""
    p = Path(WIKI_LOG_FILE)
    return p.read_text(encoding="utf-8") if p.exists() else "(wiki/log.md chưa tạo)"


# ─────────────────────────────────────────────────────────────────────────────
# Tools — search / read / list (read-only).
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def wiki_search(query: str, top_k: int = 8) -> list:
    """Hybrid search (BM25 + vector cosine) trên wiki + raw.

    Dùng cho: câu hỏi tổng quát, tìm page liên quan kèm snippet 300 chars đầu.
    Trả về list[{path, title, category, score, snippet}] sắp theo score giảm dần.
    """
    try:
        return search.hybrid_search(_conn(), query, top_k=top_k, provider=_provider())
    except Exception as e:
        log.exception("wiki_search failed")
        return [_err(f"search error: {e}")]


@mcp.tool()
def semantic_search(query: str, top_k: int = 6) -> list:
    """Semantic chunk-level search (cần `rag/index.py` build trước).

    Dùng cho: câu hỏi về passage cụ thể trong page dài — vector cosine trên chunks.
    Trả về list[{path, chunk, score, snippet}].
    """
    try:
        return rag_search.semantic_search(query, top_k=top_k)
    except Exception as e:
        log.warning("semantic_search unavailable: %s", e)
        return [_err(f"rag index chưa build hoặc lỗi: {e}",
                     hint="chạy `python rag/index.py` để build index")]


@mcp.tool()
def wiki_read(path: str) -> dict:
    """Đọc nguyên nội dung 1 file (wiki page hoặc raw source).

    Args:
        path: đường dẫn tương đối từ repo root, ví dụ 'wiki/tech/index.md'.
    """
    full = _resolve(path)
    if full is None:
        return _err(f"path ngoài WIKI_ROOT: {path}")
    if not full.exists():
        return _err(f"not found: {path}")
    return {"path": path, "content": full.read_text(encoding="utf-8")}


@mcp.tool()
def wiki_list(domain: str = "", kind: str = "", category: str = "") -> list:
    """Liệt kê wiki pages đã index. Lọc theo domain (top-level folder) hoặc kind (entity|concept|source|task).

    Args:
        domain: filter theo domain, vd 'tech', 'expo-ecosystem', 'minna-no-nihongo'. Rỗng = all.
        kind: filter theo semantic role. Rỗng = all.
        category: LEGACY alias cho domain (tech|projects|languages) — ưu tiên `domain` nếu cả hai truyền.

    Mỗi entry là {path, title, domain, kind, category}. Domain có thể là bất kỳ tên folder top-level nào.
    """
    dom = domain or category or None
    return db.list_pages(_conn(), domain=dom, kind=kind or None)


@mcp.tool()
def list_raw_source(subdir: str = "inbox") -> list:
    """Liệt kê nguồn thô trong raw/<subdir>/ (mặc định 'inbox').

    Dùng để agent khám phá nguồn chưa ingest. Trả về list filename.
    """
    d = RAW_DIR / subdir
    if not d.is_dir():
        return []
    return sorted(
        f.name for f in d.iterdir() if f.is_file() and not f.name.startswith(".")
    )


@mcp.tool()
def read_raw_source(name: str, subdir: str = "inbox") -> dict:
    """Đọc nguồn gốc từ raw/<subdir>/<name> — để agent cite provenance.

    Args:
        name: filename, ví dụ '2026-08-foo.md'.
        subdir: thư mục con trong raw/, mặc định 'inbox'.
    """
    full = _resolve(str(Path("raw") / subdir / name))
    if full is None or not full.exists():
        return _err(f"not found: raw/{subdir}/{name}")
    return {"path": f"raw/{subdir}/{name}", "content": full.read_text(encoding="utf-8")}


# ─────────────────────────────────────────────────────────────────────────────
# Tools — WRITE có kiểm soát. Không bao giờ ghi thẳng wiki/.
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def wiki_submit(
    title: str,
    content: str,
    domain: str = "",
    source: str = "",
    category: str = "",
) -> dict:
    """NẠP NGỮ CẢNH DUY NHẤT ĐƯỢC PHÉP QUA MCP: ghi vào raw/inbox/.

    Dùng để AI khác đóng góp dự án / task / tài liệu. Maintainer (wiki maintainer
    agent) sẽ ingest từ inbox → wiki sau khi human duyệt. Tool này KHÔNG lên wiki.

    Args:
        title: tiêu đề — cũng dùng làm slug filename.
        content: nội dung markdown (không cần frontmatter — tool tự thêm).
        domain: gợi ý domain (top-level folder), vd 'tech', 'expo-ecosystem', 'minna-no-nihongo'.
                Rỗng = maintainer tự detect khi ingest.
        source: URL / citation gốc (tùy chọn, cho provenance).
        category: LEGACY alias cho domain (tech|projects|languages). Ưu tiên `domain` nếu cả hai truyền.
    """
    RAW_INBOX.mkdir(parents=True, exist_ok=True)
    fname = f"{_slug(title)}.md"
    full = RAW_INBOX / fname
    if full.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        full = RAW_INBOX / f"{_slug(title)}-{stamp}.md"
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
    rel = str(full.relative_to(WIKI_ROOT))
    log.info("submitted to inbox: %s (domain=%s)", rel, dom)
    return {
        "submitted": rel,
        "domain": dom,
        "note": "Đã nạp vào raw/inbox. Chờ wiki maintainer ingest lên wiki (không tự lên wiki).",
    }


@mcp.tool()
def wiki_propose_edit(path: str, content: str) -> dict:
    """ĐỀ XUẤT sửa wiki (staging). Ghi vào wiki/.proposals/, KHÔNG sửa wiki trực tiếp.

    Args:
        path: path wiki page mục tiêu, ví dụ 'wiki/tech/foo.md'.
        content: nội dung markdown mới đề xuất.

    Returns:
        dict với 'staged' (path proposal), 'target' (path wiki), 'note'.
    """
    if _resolve(path) is None:
        return _err(f"target path ngoài WIKI_ROOT: {path}")
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", os.path.basename(path))
    prop_path = PROPOSALS_DIR / f"{stamp}__{safe}"
    prop_path.write_text(content, encoding="utf-8")
    log.info("proposal staged: %s → %s", prop_path.relative_to(WIKI_ROOT), path)
    return {
        "staged": str(prop_path.relative_to(WIKI_ROOT)),
        "target": path,
        "note": "Human review proposal trước khi apply vào wiki.",
    }


@mcp.tool()
def wiki_lint() -> dict:
    """Health-check wiki: orphan pages, broken [[wikilinks]], missing file trên disk.

    Chạy định kỳ hoặc sau ingest lớn. Contradiction KHÔNG tự resolve — report cho human.
    """
    return lintmod.lint(_conn())


if __name__ == "__main__":
    log.info("starting llm-wiki-mcp (stdio)")
    try:
        mcp.run()
    except KeyboardInterrupt:
        log.info("interrupted")
        sys.exit(0)
