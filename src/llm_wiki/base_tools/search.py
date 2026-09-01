import logging
import math
import os

import db
from embed import EmbedProvider

log = logging.getLogger("llm-wiki.search")

BM25_WEIGHT = float(__import__("os").environ.get("WIKI_BM25_WEIGHT", "0.5"))
VEC_WEIGHT = float(__import__("os").environ.get("WIKI_VEC_WEIGHT", "0.5"))


def _cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def hybrid_search(conn, query, top_k=8, provider=None):
    """Trả về list[{path,title,domain,kind,score,snippet}] — hybrid BM25 + vector cosine."""
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
            score += BM25_WEIGHT * bm25[r["id"]]
        emb = None
        if r["embedding"]:
            import json

            emb = json.loads(r["embedding"])
        if qvec is not None and emb:
            score += VEC_WEIGHT * _cosine(qvec, emb)
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


def index_file(conn, path, title, domain, kind, content, provider=None, category=""):
    """Index 1 page với metadata mới (domain/kind). `category` legacy — để trống cho page mới."""
    emb = None
    if provider is not None:
        try:
            emb = provider.embed([content])[0]
        except Exception as e:
            log.warning("embed skip (%s); BM25-only", e)
    mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
    db.upsert_page(conn, path, title, domain, kind, content, mtime, emb, category=category)


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
    index_file(conn, rel, title, domain, kind, content, provider, category=category)


if __name__ == "__main__":
    c = db.get_conn()
    db.init_db(c)
    prov = EmbedProvider()
    print(hybrid_search(c, "vector search", provider=prov))
