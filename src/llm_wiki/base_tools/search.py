import hashlib
import json
import logging
import math
import os
import re

import db
from config_file import get_config, effective
from embed import EmbedProvider, DEFAULT_MODEL

log = logging.getLogger("llm-wiki.search")


def _retrieval_settings():
    """Đọc retrieval config per-call (MCP _set_wiki_ctx đổi WIKI_ROOT per-wiki → cấm module-level).

    Precedence: env (WIKI_BM25_WEIGHT/WIKI_VEC_WEIGHT) > TOML > builtin default.
    """
    cfg = get_config(db.WIKI_ROOT)
    r = cfg["retrieval"]
    bm25_weight = float(effective("WIKI_BM25_WEIGHT", r.get("bm25_weight") or None, 0.5))
    vec_weight = float(effective("WIKI_VEC_WEIGHT", r.get("vec_weight") or None, 0.5))
    relax_recall = bool(r.get("relax_recall", True))
    vector_enabled = bool(r.get("vector", False))
    return bm25_weight, vec_weight, relax_recall, vector_enabled


def _cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _fts_or_query(query: str) -> str:
    r"""Build OR-query từ các term của query (relax_recall fallback, CJK-safe).

    Sanitize mỗi term về \w+ (giữ unicode letters/digits/CJK) — ký tự như `-`,
    `"`, `()` làm FTS5 query parser lỗi hoặc đổi ngữ nghĩa.
    """
    terms = [re.sub(r"[^\w]+", "", t) for t in query.split()]
    return " OR ".join(t for t in terms if t)


def hybrid_search(conn, query, top_k=8, provider=None):
    """Trả về list[{path,title,domain,kind,score,snippet}] — hybrid BM25 + vector cosine."""
    bm25_weight, vec_weight, relax_recall, vector_enabled = _retrieval_settings()
    if not vector_enabled:
        # vector=false → BM25-only (fallback tất định: thiếu model ≠ hỏng)
        provider = None

    # BM25 via FTS5
    bm25 = {}
    try:
        cur = conn.execute(
            "SELECT rowid, bm25(pages_fts) AS s FROM pages_fts WHERE pages_fts MATCH ?",
            (query,),
        )
        for r in cur.fetchall():
            bm25[r["rowid"]] = -r["s"]
    except Exception:
        bm25 = {}
    if not bm25 and relax_recall:
        # AND-match 0 kết quả → thử lại OR một lần
        or_query = _fts_or_query(query)
        if or_query and or_query != query:
            try:
                cur = conn.execute(
                    "SELECT rowid, bm25(pages_fts) AS s FROM pages_fts WHERE pages_fts MATCH ?",
                    (or_query,),
                )
                for r in cur.fetchall():
                    bm25[r["rowid"]] = -r["s"]
            except Exception:
                bm25 = {}

    rows = conn.execute(
        "SELECT id, path, title, domain, kind, content, embedding FROM pages"
    ).fetchall()

    qvec = None
    if provider is not None and rows:
        qvec = provider.embed([query])[0]

    results = []
    for r in rows:
        score = 0.0
        matched = r["id"] in bm25
        if matched:
            score += bm25_weight * bm25[r["id"]]
        emb = None
        if r["embedding"]:
            emb = json.loads(r["embedding"])
        if qvec is not None and emb:
            score += vec_weight * _cosine(qvec, emb)
            matched = True
        if matched:
            results.append(
                {
                    "path": r["path"],
                    "title": r["title"],
                    "domain": r["domain"],
                    "kind": r["kind"],
                    "score": round(score, 4),
                    "snippet": (r["content"] or "")[:300],
                }
            )
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def _title_from_content(content: str, fallback: str) -> str:
    """Lấy title từ H1 đầu tiên của markdown (bỏ qua frontmatter), fallback path."""
    if not content:
        return fallback
    # Skip frontmatter
    text = content
    if text.startswith("---"):
        # find closing ---
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                text = "\n".join(lines[i + 1 :])
                break
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line.lstrip("# ").strip() or fallback
    return fallback


def index_file(conn, path, title, domain, kind, content, provider=None, category="", content_hash=None):
    """Index 1 page với metadata mới (domain/kind). `category` legacy — để trống cho page mới."""
    emb = None
    if provider is not None:
        try:
            emb = provider.embed([content])[0]
        except Exception as e:
            log.warning("embed skip (%s); BM25-only", e)
    mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
    db.upsert_page(conn, path, title, domain, kind, content, mtime, emb, category=category, content_hash=content_hash)


def index_file_at(conn, full, provider=None):
    """Index 1 file bất kỳ (raw/ hoặc wiki/) vào DB, parse frontmatter để lấy domain/kind."""
    rel = os.path.relpath(full, db.WIKI_ROOT)
    with open(full, encoding="utf-8") as f:
        content = f.read()
    domain, kind = db.extract_domain_kind(content, rel)
    title = _title_from_content(content, rel)
    # legacy: nếu path dưới wiki/ nhưng không có domain/kind, suy ra category legacy
    category = ""
    if rel.startswith("wiki/") and domain in db.LEGACY_CATEGORIES and not kind:
        category = domain
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    index_file(conn, rel, title, domain, kind, content, provider, category=category, content_hash=content_hash)


if __name__ == "__main__":
    c = db.get_conn()
    db.init_db(c)
    prov = EmbedProvider()
    print(hybrid_search(c, "vector search", provider=prov))
