"""Search + indexing layer: union retrieval (BM25 page / BM25 chunk / vector chunk) + RRF fusion.

Markdown là nguồn sự thật; DB FTS + rag/.rag_index là derived (idea.md:155).

Kiến trúc (docs/tier3-roadmap.md §2-§3):
    query ─┬─ bm25_page    : pages_fts MATCH             (luôn chạy)
           ├─ bm25_chunk   : chunks_fts MATCH → page_id   (chunk_bm25=true)
           ├─ vector_chunk : chunks.json × vectors.npy    (vector=true)
           └─ vector_page  : pages.embedding              (CHỈ khi fusion="weighted")
                                ↓ RRF trên HẠNG (không trên score)
                        page metadata + snippet + matched_by

Vì sao RRF: bm25() không có thang cố định còn cosine ∈ [-1,1]; weighted sum
(Tier 1) cộng thẳng hai độ lớn khác nhau nên channel BM25 áp đảo. RRF chỉ nhìn
hạng → khỏi normalize, và tự khử trùng theo page.

Fallback tất định (idea.md:162 "không model ≠ hỏng"): mỗi kênh tự tắt khi hạ
tầng thiếu — chunks_fts vắng/rỗng, vectors.npy chưa build, provider None, numpy
thiếu. Không bao giờ raise.

`pages.embedding` vẫn được ghi khi `vector=true` nhưng RRF KHÔNG đọc nó — RRF
chỉ fusion trên HẠNG của 3 kênh bm25_page / bm25_chunk / vector_chunk. Cột đó
chỉ phục vụ `fusion="weighted"` (hành vi Tier 1: weighted sum BM25 + cosine,
giữ làm rollback/baseline cho `eval --compare`). Đừng xoá: xoá là mất baseline.

Mọi setting đọc PER-CALL (`_retrieval_settings`, `rag_index_dir`), không
module-level: centralized MCP `_set_wiki_ctx` đổi `db.WIKI_ROOT` + env giữa các
lệnh trong cùng một process.
"""
import hashlib
import json
import logging
import math
import os
import re

import db
from chunking import chunk_markdown, clean_body, is_reserved
from config_file import effective, get_config
from embed import EmbedProvider

log = logging.getLogger("llm-wiki.search")

_WARNED_NO_CHUNKS = False  # nhắc 1 lần/process, không spam mỗi query

# Cache chunk-vector, key = (chunks.json path, mtime, size, vectors path, mtime, size).
# MCP là process dài ngày; đọc + parse cả chunks.json mỗi query là lãng phí, và
# `eval --compare` phóng đại nó lên (3 profile × N query). Mtime làm reindex tự
# hợp lệ hoá — không có chuyện dùng chỉ mục cũ sau khi reindex.
_VECTOR_CACHE: dict = {}
_VECTOR_CACHE_MAX = 6

# Lỗi làm MỘT kênh tắt hẳn, theo tên kênh. Fallback tất định là cố ý (thiếu model
# ≠ hỏng), nhưng "kênh chết im lặng" sẽ biến eval thành số liệu GIẢ — nên ghi lại
# để `llm-wiki eval` in ra. Xoá sạch mỗi lần hybrid_search chạy.
CHANNEL_ERRORS: dict = {}


def _channel_off(channel: str, err) -> None:
    """Ghi + log lý do một kênh bị tắt (không raise)."""
    CHANNEL_ERRORS[channel] = str(err)
    log.warning("%s tắt vì lỗi: %s", channel, err)


def _bool_env(env_name: str, toml_val) -> bool:
    """Bool env override: '0'/'false'/'no'/'off' = False; giá trị khác = True."""
    env = os.environ.get(env_name)
    if env is not None and env != "":
        return env.strip().lower() not in ("0", "false", "no", "off")
    return bool(toml_val)


def _retrieval_settings() -> dict:
    """Effective retrieval config, đọc per-call. Precedence: env > TOML > builtin.

    Không cache: `get_config` parse file TOML ~1KB (sub-ms), còn cache lại đúng
    class bug Tier 1 đã sửa (config cũ bị đóng băng trong process dài của MCP).
    """
    cfg = get_config(db.WIKI_ROOT)
    r = cfg["retrieval"]
    weights = dict(r.get("weights") or {})
    # RRF chỉ nhạy TỈ số weight → seed từ bm25_weight/vec_weight để env override
    # cũ vẫn có nghĩa; 0.5/0.5 tương đương 1.0/1.0.
    weights.setdefault("bm25_page", float(r.get("bm25_weight", 0.5)))
    weights.setdefault("bm25_chunk", float(r.get("bm25_weight", 0.5)))
    weights.setdefault("vector", float(r.get("vec_weight", 0.5)))
    return {
        "mode": str(r.get("mode", "hybrid")),             # bm25 | hybrid
        "fusion": str(effective("WIKI_FUSION", r.get("fusion") or None, "rrf")),  # rrf | weighted
        "rrf_k": int(r.get("rrf_k", 60)),
        "chunk_bm25": _bool_env("WIKI_CHUNK_BM25", r.get("chunk_bm25", True)),
        "vector": bool(r.get("vector", False)),
        "relax_recall": bool(r.get("relax_recall", True)),
        "rerank": str(r.get("rerank", "llm")),            # skill layer đọc, Python không dùng
        "top_k_bm25": int(r.get("top_k_bm25", 20)),
        "top_k_vector": int(r.get("top_k_vector", 20)),
        "top_n_final": int(r.get("top_n_final", 8)),
        "bm25_weight": float(effective("WIKI_BM25_WEIGHT", r.get("bm25_weight") or None, 0.5)),
        "vec_weight": float(effective("WIKI_VEC_WEIGHT", r.get("vec_weight") or None, 0.5)),
        "weights": weights,
        "chunk_tokens": int(r.get("chunk_tokens", 512)),
    }


def rag_index_dir() -> str:
    """Thư mục chunk-vector, resolve PER-CALL: env `RAG_INDEX_DIR` > `<root>/rag/.rag_index`.

    Module constant (kiểu `base_rag/search.py:19-21`) không sống được với MCP
    multi-wiki vì `_set_wiki_ctx` đổi root từng lệnh.
    """
    env = os.environ.get("RAG_INDEX_DIR")
    if env:
        return env if os.path.isabs(env) else os.path.join(str(db.WIKI_ROOT), env)
    return os.path.join(str(db.WIKI_ROOT), "rag", ".rag_index")


def _cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _fts_terms(query: str) -> list:
    r"""Tách query thành term \w+ thuần, giữ thứ tự, bỏ trùng.

    Vì sao phải TÁCH chứ không bỏ ký tự: tokenizer mặc định của FTS5 (unicode61)
    cắt `kumquat-xray-77` thành 3 token `kumquat`/`xray`/`77`. Bản sanitize cũ
    (`re.sub(r"[^\w]+", "", term)`) DÍNH chúng lại thành `kumquatxray77` → mọi
    identifier có dấu `-` / `_` / `.` đều không bao giờ match.
    """
    seen, out = set(), []
    for t in re.findall(r"\w+", query or "", flags=re.UNICODE):
        tl = t.lower()
        if tl and tl not in seen:
            seen.add(tl)
            out.append(tl)
    return out


def _fts_or_query(query: str) -> str:
    r"""OR-query các term (relax_recall fallback, CJK-safe — \w+ giữ letter/digit/CJK)."""
    return " OR ".join(_fts_terms(query))


def _fts_and_query(query: str) -> str:
    """AND-query các term đã sanitize — an toàn cú pháp FTS5."""
    return " AND ".join(_fts_terms(query))


def _query_attempts(query: str, relax_recall: bool) -> list:
    """Thứ tự thử: query nguyên bản (giữ quyền dùng cú pháp FTS5 của user) →
    AND các term sanitize → OR các term (chỉ khi relax_recall).

    Mỗi lượt chạy trong 1 try/except riêng (`_fts_ranked`): query chứa `-`, `"`,
    `()` làm FTS5 parser lỗi sẽ tự rơi xuống lượt sanitize thay vì mất cả kênh.
    """
    attempts = [query]
    and_q = _fts_and_query(query)
    if and_q and and_q not in attempts:
        attempts.append(and_q)
    if relax_recall:
        or_q = _fts_or_query(query)
        if or_q and or_q not in attempts:
            attempts.append(or_q)
    return attempts


def _table_exists(conn, name: str) -> bool:
    try:
        return db.table_exists(conn, name)
    except Exception:
        return False


def _fts_ranked(conn, table: str, extra_cols: list, query: str, limit: int,
                relax_recall: bool) -> list:
    """Ranked rows từ FTS5 MATCH, mỗi row có `score` = -bm25() (lớn = tốt hơn).

    Thử lần lượt các biến thể query (`_query_attempts`): giữ nguyên → AND sanitize
    → OR khi `relax_recall`. Chuyển sang lượt kế khi lượt trước **lỗi cú pháp HOẶC
    trả 0 dòng** — 0 dòng là trường hợp phổ biến với tiếng Việt (một stopword như
    "là"/"gì" làm AND fail dù các term chính có match).
    Lỗi ở mọi lượt (bảng thiếu, FTS5 không có) → [] — kênh tự tắt, không hỏng search.
    """
    cols = "".join(f"{c}, " for c in extra_cols)
    sql = (
        f"SELECT rowid, {cols}-bm25({table}) AS score "
        f"FROM {table} WHERE {table} MATCH ? ORDER BY bm25({table}) LIMIT ?"
    )
    last_err = None
    ran_cleanly = False
    for q in _query_attempts(query, relax_recall):
        try:
            rows = [dict(r) for r in conn.execute(sql, (q, limit)).fetchall()]
        except Exception as e:
            last_err = e
            continue
        ran_cleanly = True
        if rows:
            return rows
    # Chỉ báo "kênh tắt vì lỗi" khi KHÔNG lượt nào chạy được về mặt cú pháp.
    # Nếu có một lượt sạch nhưng 0 kết quả → kênh vẫn sống, chỉ là không có gì
    # match; báo lỗi ở đây là false alarm làm người dùng nghi ngờ tín hiệu thật.
    if not ran_cleanly and last_err is not None:
        _channel_off(table, last_err)
    return []


def _rrf(rank_lists: list, weights: dict, k: int) -> dict:
    """Reciprocal rank fusion: R(d) = Σ_channels w_channel / (k + rank).

    `rank_lists` = [(channel_name, [item_id theo hạng giảm dần]), ...].
    Trả dict item_id -> fused score; item xuất hiện ở nhiều kênh tự được cộng dồn
    (đó là toàn bộ ý nghĩa của "union + khử trùng").
    """
    fused: dict = {}
    for name, ranked in rank_lists:
        w = float(weights.get(name, 1.0))
        if not w:
            continue
        for pos, item in enumerate(ranked, start=1):
            fused[item] = fused.get(item, 0.0) + w / (k + pos)
    return fused


def rrf_fuse(rank_lists: list, weights: dict | None = None, k: int = 60) -> dict:
    """Public alias của `_rrf` — dùng cho fusion cross-wiki trong MCP server."""
    return _rrf(rank_lists, weights or {}, k)


def _trim(text: str, limit: int = 300) -> str:
    """Snippet gọn ở ranh giới câu nếu có thể — skill rerank bằng cách ĐỌC snippet."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    for sep in (". ", "\n", "; "):
        cut = head.rfind(sep)
        if cut > limit // 2:
            return head[: cut + len(sep)].strip()
    return head.strip()


# ── chunk sync (BM25 chunk-level) ────────────────────────────────────────────


def sync_chunks(conn, page_id: int, path: str, content: str, chunk_tokens: int) -> int:
    """Dựng lại chunk của 1 page trong `chunks_fts` (DELETE-then-INSERT, idempotent).

    Chỉ index page dưới `wiki/`, trừ reserved (index.md/log.md) — cùng luật với
    `rag/index.py:_collect_files` để 2 kênh chunk dùng chung ranh giới.
    Trả số chunk đã ghi (0 nếu page không đủ điều kiện).
    """
    if not _table_exists(conn, "chunks_fts"):
        return 0
    rel = path.replace(os.sep, "/")
    try:
        conn.execute("DELETE FROM chunks_fts WHERE page_id = ?", (page_id,))
    except Exception:
        return 0
    n = 0
    if rel.startswith("wiki/") and not is_reserved(rel):
        max_chars = max(200, int(chunk_tokens) * 4)
        for i, ch in enumerate(chunk_markdown(content, max_chars)):
            conn.execute(
                "INSERT INTO chunks_fts(text, path, chunk_idx, page_id) VALUES(?,?,?,?)",
                (ch, rel, i, page_id),
            )
            n += 1
    # db.upsert_page commit TRƯỚC khi hàm này chạy → phải commit riêng, nếu không
    # chunk mất hút với ingest đơn file (`llm-wiki ingest`).
    conn.commit()
    return n


def chunk_count(conn) -> int:
    if not _table_exists(conn, "chunks_fts"):
        return 0
    try:
        return int(conn.execute("SELECT count(*) FROM chunks_fts").fetchone()[0])
    except Exception:
        return 0


def _warn_no_chunks():
    """chunks_fts rỗng (wiki chưa reindex sau upgrade) → nhắc 1 lần, không hỏng search."""
    global _WARNED_NO_CHUNKS
    if _WARNED_NO_CHUNKS:
        return
    _WARNED_NO_CHUNKS = True
    log.warning("chunks_fts rỗng — chạy `llm-wiki reindex --full` để bật kênh bm25_chunk")


# ── channels: mỗi kênh trả (ranked list, snippets) ───────────────────────────
# ranked list: [(page_id, score)] theo hạng giảm dần
# snippets   : {page_id: text}  (chunk/đoạn sát nhất, để skill rerank không phải mở file)


def _channel_bm25_page(conn, query: str, s: dict):
    if not _table_exists(conn, "pages_fts"):
        return [], {}
    rows = _fts_ranked(conn, "pages_fts", [], query, s["top_k_bm25"], s["relax_recall"])
    return [(r["rowid"], r["score"]) for r in rows if r.get("rowid") is not None], {}


def _channel_bm25_chunk(conn, query: str, s: dict):
    """Chunk-level BM25 → gom về page theo hạng chunk tốt nhất.

    Page dài nghìn dòng bị page-level BM25 dilute; chunk thì không — đây là lý
    do kênh này tồn tại (roadmap §3).
    """
    if not s["chunk_bm25"] or not _table_exists(conn, "chunks_fts"):
        return [], {}
    limit = max(s["top_k_bm25"] * 4, 20)
    rows = _fts_ranked(
        conn, "chunks_fts", ["page_id", "text"], query, limit, s["relax_recall"]
    )
    if not rows and chunk_count(conn) == 0:
        _warn_no_chunks()
    ranked, snippets, seen = [], {}, set()
    for r in rows:
        pid = r.get("page_id")
        if pid is None or pid in seen:
            continue
        seen.add(pid)
        ranked.append((pid, r["score"]))
        snippets[pid] = r.get("text") or ""
    return ranked, snippets


def _channel_vector_chunk(query: str, provider, s: dict):
    """Chunk-level cosine từ rag/.rag_index — trả (ranked [(path, score)], snippets).

    Tự tắt khi: provider None, vector=false, mode=bm25, chưa build index, numpy
    thiếu, hoặc index hỏng (len mismatch).
    """
    if provider is None or not s["vector"] or s["mode"] == "bm25":
        return [], {}
    index_dir = rag_index_dir()
    vectors_file = os.path.join(index_dir, "vectors.npy")
    chunks_file = os.path.join(index_dir, "chunks.json")
    if not (os.path.exists(vectors_file) and os.path.exists(chunks_file)):
        return [], {}
    try:
        import numpy as np
    except ImportError as e:
        _channel_off("vector_chunk", e)
        return [], {}
    try:
        key = (
            chunks_file, os.path.getmtime(chunks_file), os.path.getsize(chunks_file),
            vectors_file, os.path.getmtime(vectors_file), os.path.getsize(vectors_file),
        )
        cached = _VECTOR_CACHE.get(key)
        if cached is None:
            with open(chunks_file, encoding="utf-8") as f:
                meta = json.load(f)
            arr = np.load(vectors_file)
            if len(_VECTOR_CACHE) >= _VECTOR_CACHE_MAX:
                _VECTOR_CACHE.clear()
            _VECTOR_CACHE[key] = (meta, arr)
        else:
            meta, arr = cached
        if arr.size == 0 or not meta or len(meta) != len(arr):
            return [], {}
        q = np.array(provider.embed([query])[0], dtype="float32")
        q = q / (np.linalg.norm(q) + 1e-9)
        # norms[:, None]: chia theo TỪNG hàng. Quên [:, None] → broadcast (N,D)/(N,)
        # lỗi, và except ở dưới nuốt thành "kênh tắt" — số liệu eval sẽ giả.
        norms = np.linalg.norm(arr, axis=1) + 1e-9
        sims = (arr / norms[:, None]) @ q
        idx = sims.argsort()[::-1][: s["top_k_vector"]]
        ranked, snippets, seen = [], {}, set()
        for i in idx:
            path = meta[i]["path"]
            if path in seen:
                continue
            seen.add(path)
            ranked.append((path, float(sims[i])))
            snippets[path] = meta[i]["text"]
        return ranked, snippets
    except Exception as e:  # index hỏng/cấu trúc lệch → fallback, không hỏng search
        _channel_off("vector_chunk", e)
        return [], {}


# ── search entry point ───────────────────────────────────────────────────────


def hybrid_search(conn, query, top_k=None, provider=None, settings=None):
    """Union retrieval + RRF fusion.

    Trả list[{path,title,domain,kind,score,snippet,matched_by,rank}].

    Args:
        conn: sqlite connection (đã `init_db`).
        query: câu hỏi/keyword.
        top_k: số kết quả CUỐI (không phải mỗi kênh). None/0 → `[retrieval].top_n_final`.
        provider: EmbedProvider hoặc None — kênh vector tự tắt khi None.
        settings: override `_retrieval_settings()`. `eval --compare` dùng để đổi
            profile mà không monkeypatch module.

    `fusion="weighted"` tái hiện ĐÚNG hành vi Tier 1 (weighted sum + full table
    scan + page embedding) — giữ làm rollback và làm baseline đo được.
    """
    s = settings or _retrieval_settings()
    n_final = top_k if (top_k and top_k > 0) else s["top_n_final"]
    CHANNEL_ERRORS.clear()
    if s["fusion"] == "weighted":
        return _weighted_search(conn, query, n_final, provider, s)
    return _rrf_search(conn, query, n_final, provider, s)


def _rrf_search(conn, query, n_final, provider, s):
    rank_lists: list = []
    channels_by_page: dict = {}
    snippets: dict = {}

    page_ranked, _ = _channel_bm25_page(conn, query, s)
    if page_ranked:
        rank_lists.append(("bm25_page", [pid for pid, _ in page_ranked]))
        for pid, _ in page_ranked:
            channels_by_page.setdefault(pid, []).append("bm25_page")

    chunk_ranked, chunk_snips = _channel_bm25_chunk(conn, query, s)
    if chunk_ranked:
        rank_lists.append(("bm25_chunk", [pid for pid, _ in chunk_ranked]))
        for pid, _ in chunk_ranked:
            channels_by_page.setdefault(pid, []).append("bm25_chunk")
        for pid, snip in chunk_snips.items():
            snippets[pid] = snip

    vec_ranked, vec_snips = _channel_vector_chunk(query, provider, s)
    if vec_ranked:
        path_to_id = _path_to_id(conn, [p for p, _ in vec_ranked])
        vec_ids = [path_to_id[p] for p, _ in vec_ranked if p in path_to_id]
        if vec_ids:
            rank_lists.append(("vector_chunk", vec_ids))
        for p, _ in vec_ranked:
            pid = path_to_id.get(p)
            if pid is not None:
                channels_by_page.setdefault(pid, []).append("vector_chunk")
        for p, snip in vec_snips.items():
            pid = path_to_id.get(p)
            if pid is not None:
                snippets.setdefault(pid, snip)

    if not rank_lists:
        return []

    fused = _rrf(rank_lists, s["weights"], s["rrf_k"])
    # tie-break theo page_id để thứ tự ổn định giữa các lần chạy (cần cho eval)
    ordered = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))[:n_final]
    if not ordered:
        return []

    ids = [pid for pid, _ in ordered]
    placeholders = ",".join("?" * len(ids))
    rows = {
        r["id"]: dict(r)
        for r in conn.execute(
            f"SELECT id, path, title, domain, kind, content FROM pages WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    }
    results = []
    for pid, score in ordered:
        row = rows.get(pid)
        if not row:  # id lạ trong FTS (markdown đã xoá, chưa reindex) — bỏ, không đếm hạng
            continue
        snippet = snippets.get(pid) or clean_body(row["content"] or "")
        results.append(
            {
                "path": row["path"],
                "title": row["title"],
                "domain": row["domain"],
                "kind": row["kind"],
                "score": round(score, 6),
                "snippet": _trim(snippet),
                "matched_by": channels_by_page.get(pid, []),
                "rank": len(results) + 1,
            }
        )
    return results


def _path_to_id(conn, paths: list) -> dict:
    paths = [p.replace(os.sep, "/") for p in paths]
    if not paths:
        return {}
    placeholders = ",".join("?" * len(paths))
    cur = conn.execute(
        f"SELECT id, path FROM pages WHERE path IN ({placeholders})", paths
    )
    return {r["path"]: r["id"] for r in cur.fetchall()}


def _weighted_search(conn, query, top_k, provider, s):
    """Hành vi Tier 1: weighted sum BM25 + cosine trên page embedding, full table scan.

    Giữ nguyên để (a) rollback bằng 1 dòng `fusion = "weighted"`, (b) eval
    `--compare` có baseline tái hiện đúng hành vi cũ.
    """
    if not s["vector"]:
        provider = None
    page_ranked, _ = _channel_bm25_page(conn, query, s)
    bm25 = {pid: score for pid, score in page_ranked}

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
        channels = ["bm25_page"] if matched else []
        if matched:
            score += s["bm25_weight"] * bm25[r["id"]]
        emb = None
        if r["embedding"]:
            emb = json.loads(r["embedding"])
        if qvec is not None and emb:
            score += s["vec_weight"] * _cosine(qvec, emb)
            matched = True
            channels.append("vector_page")
        if matched:
            results.append(
                {
                    "path": r["path"],
                    "title": r["title"],
                    "domain": r["domain"],
                    "kind": r["kind"],
                    "score": round(score, 4),
                    "snippet": (r["content"] or "")[:300],  # nguyên như Tier 1
                    "matched_by": channels,
                }
            )
    results.sort(key=lambda x: x["score"], reverse=True)
    out = results[:top_k]
    for i, res in enumerate(out, start=1):
        res["rank"] = i
    return out


# ── indexing ─────────────────────────────────────────────────────────────────


def _title_from_content(content: str, fallback: str) -> str:
    """Lấy title từ H1 đầu tiên của markdown (bỏ qua frontmatter), fallback path."""
    if not content:
        return fallback
    text = content
    if text.startswith("---"):
        lines = text.split("\n")
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                text = "\n".join(lines[i + 1:])
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
    """Index 1 page vào pages + pages_fts + chunks_fts.

    `category` legacy chỉ dùng cho row cũ — page mới truyền category=''.
    Reserved (index.md/log.md) không phải concept → không index, xoá row cũ nếu có.
    """
    rel = path.replace(os.sep, "/")
    if rel.startswith("wiki/") and is_reserved(rel):
        db.delete_page(conn, path)
        return 0
    s = _retrieval_settings()
    emb = None
    if provider is not None and s["vector"]:
        # vector=false → không embed cả content: `pages.embedding` chỉ kênh
        # vector_page (weighted mode) đọc, mà kênh đó cũng tắt theo flag.
        try:
            emb = provider.embed([content])[0]
        except Exception as e:
            log.warning("embed skip (%s); BM25-only", e)
    mtime = os.path.getmtime(path) if os.path.exists(path) else 0.0
    pid = db.upsert_page(
        conn, path, title, domain, kind, content, mtime, emb,
        category=category, content_hash=content_hash,
    )
    sync_chunks(conn, pid, path, content, s["chunk_tokens"])
    return pid


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
    print(json.dumps(hybrid_search(c, "vector search", provider=prov), ensure_ascii=False, indent=2))
