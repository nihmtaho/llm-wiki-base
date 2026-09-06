"""Eval harness — đo chất lượng retrieval trên bộ query vàng (P@k / R@k / MRR).

Mục tiêu (docs/tier3-roadmap.md §1): biến quyết định "có bật `retrieval.vector`
không?" thành số liệu, thay vì đoán. Đồng thời là regression net cho ranking:
sau mỗi lần đổi fusion/chunking, chạy lại là biết tốt lên hay kém đi.

Chế độ:
    eval                  — đo theo config hiện tại của wiki
    eval --compare        — chạy nhiều profile, in bảng so sánh + verdict
    eval --k 10           # override cutoff (mặc định [eval].k)
    eval --json           # machine-readable
    eval --init           # tạo eval/golden.toml từ template

read-only với wiki: KHÔNG sửa markdown, KHÔNG ghi wiki/log.md (eval không phải
một operation trên knowledge). `db.init_db()` có thể tạo bảng FTS rỗng trên DB
cũ — DDL idempotent, không đụng dữ liệu.

Giới hạn: đo 1 wiki (`WIKI_ROOT`), không phủ đường gộp cross-wiki của MCP
`wiki_search` (fusion khác, ở tầng khác).
"""
import argparse
import hashlib
import json
import os
import re
import sys

import db
import search
from config_file import effective, get_config
from embed import DEFAULT_MODEL, EmbedProvider
from paths import WIKI_ROOT

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore

# Profile cho --compare. `overrides` đắp lên settings hiện tại của wiki.
# `tier1-weighted` dùng CÔNG THỨC Tier 1 (weighted sum + page embedding + không
# chunk), nhưng có 2 bản sửa lỗi tất định của Tier 3 đã áp vào cả 2 phía:
# trang FTS5 duplicate (db.upsert_page 'delete') và chuỗi relax_recall. Nghĩa là
# Δ đo được là của "RRF + chunk", không lẫn 2 bug fix kia.
PROFILES = [
    ("tier1-weighted", {"fusion": "weighted", "chunk_bm25": False, "vector": False}),
    ("rrf-text", {"fusion": "rrf", "chunk_bm25": True, "vector": False}),
    ("rrf+vector", {"fusion": "rrf", "chunk_bm25": True, "vector": True}),
]


def _golden_path(cfg: dict) -> str:
    rel = str((cfg.get("eval") or {}).get("golden") or "eval/golden.toml")
    return rel if os.path.isabs(rel) else os.path.join(str(WIKI_ROOT), rel)


def _results_path(cfg: dict) -> str:
    rel = str((cfg.get("eval") or {}).get("results") or "eval/results.json")
    return rel if os.path.isabs(rel) else os.path.join(str(WIKI_ROOT), rel)


def _template_candidates() -> list:
    """Nơi tìm template golden: global base (deployed) rồi src layout."""
    base_dir = os.environ.get("LLM_WIKI_BASE_DIR") or os.path.expanduser("~/.llm-wiki-base")
    here = os.path.dirname(os.path.abspath(__file__))
    return [
        os.path.join(base_dir, "templates", "eval-golden.toml"),
        os.path.join(os.path.dirname(here), "templates", "eval-golden.toml"),
    ]


def cmd_init(cfg: dict) -> int:
    """Tạo eval/golden.toml từ template (không ghi đè file đã có)."""
    dst = _golden_path(cfg)
    if os.path.exists(dst):
        print(f"đã tồn tại: {dst}")
        return 0
    src = next((p for p in _template_candidates() if os.path.exists(p)), None)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if src:
        with open(src, encoding="utf-8") as f:
            text = f.read()
        print(f"golden set template: {src}")
    else:
        text = (
            "# eval/golden.toml — bộ query vàng cho `llm-wiki eval`.\n"
            "# Chưa tìm thấy template trong global base — chạy `llm-wiki base install`.\n\n"
            '[[query]]\nid = "q01"\nquery = "thay bằng câu hỏi thật"\n'
            'relevant = ["wiki/<domain>/<kind>/<slug>.md"]\n'
        )
        print("[warn] không tìm thấy templates/eval-golden.toml — viết bản stub")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"đã tạo {dst} — sửa lại thành query THẬT của bạn rồi chạy `llm-wiki eval`")
    return 0


def load_golden(path: str) -> tuple[list, list]:
    """Đọc golden.toml → (queries, lỗi). Mỗi query: {id, query, relevant:list}."""
    if not os.path.exists(path):
        return [], [f"không tìm thấy golden set: {path}"]
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        return [], [f"golden set không parse được: {e}"]
    raw = data.get("query") or []
    if not isinstance(raw, list) or not raw:
        return [], [f"{path} không có mục [[query]] nào"]
    queries, errors = [], []
    seen_ids: set = set()
    for i, item in enumerate(raw):
        qid = str(item.get("id") or f"q{i + 1:02d}")
        text = str(item.get("query") or "").strip()
        rel = item.get("relevant") or []
        if isinstance(rel, str):
            rel = [rel]
        if not text:
            errors.append(f"{qid}: thiếu `query`")
            continue
        if not rel:
            errors.append(f"{qid}: `relevant` rỗng → không đo được, bỏ qua")
            continue
        if qid in seen_ids:
            errors.append(f"{qid}: trùng id, chỉ tính lần đầu")
            continue
        seen_ids.add(qid)
        queries.append({"id": qid, "query": text, "relevant": [str(x) for x in rel]})
    return queries, errors


def norm_path(p: str) -> str:
    """Chuẩn hoá concept path để so khớp: bỏ `wiki/` đầu, bỏ `.md` cuối, lowercase.

    DB lưu `wiki/<domain>/<kind>/<slug>.md`; docs/ý người viết thường chỉ viết
    `wiki/<domain>/<kind>/<slug>` hoặc `<domain>/<kind>/<slug>`.
    """
    p = (p or "").replace(os.sep, "/").strip().strip("/")
    p = re.sub(r"^wiki/", "", p, flags=re.I)
    p = re.sub(r"\.md$", "", p, flags=re.I)
    return p.lower()


def _metrics(k: int, got: list, relevant_norm: set) -> dict:
    """P@k / R@k / MRR cho MỘT query. `got` = path kết quả theo hạng giảm dần."""
    norm = [norm_path(g) for g in got]
    hits = [n for n in norm if n in relevant_norm]
    precision = len(hits) / k if k else 0.0
    recall = len(set(hits) & relevant_norm) / len(relevant_norm) if relevant_norm else 0.0
    rr = 0.0
    for pos, n in enumerate(norm, start=1):
        if n in relevant_norm:
            rr = 1.0 / pos
            break
    return {
        "precision_at_k": round(precision, 4),
        "recall_at_k": round(recall, 4),
        "mrr": round(rr, 4),
        "hit": 1 if hits else 0,
        "first_hit_rank": int(1 / rr) if rr else None,
    }


def evaluate_profile(conn, queries, provider, settings, k) -> dict:
    """Chạy toàn bộ query vàng với MỘT profile `settings` (đã merge xong).

    Kênh nào chết giữa đường (`search.CHANNEL_ERRORS`) được gom lại vào
    `channel_errors` — một kênh tắt im lặng sẽ cho số liệu GIẢ, nên bắt buộc
    phải in ra chứ không được để nó đội tên profile khác.
    """
    per_query = []
    channel_errors: dict = {}
    for item in queries:
        try:
            res = search.hybrid_search(
                conn, item["query"], top_k=k, provider=provider, settings=settings
            )
        except Exception as e:
            res = []
            channel_errors.setdefault("hybrid_search", str(e))
            print(f"  [error] {item['id']}: {e}")
        channel_errors.update(search.CHANNEL_ERRORS)
        rel_norm = {norm_path(x) for x in item["relevant"]}
        m = _metrics(k, [r["path"] for r in res], rel_norm)
        m["id"] = item["id"]
        m["query"] = item["query"]
        m["returned"] = [r["path"] for r in res][:k]
        m["matched_by"] = [r.get("matched_by", []) for r in res][:k]
        per_query.append(m)
    n = len(per_query) or 1
    agg = {
        "p_at_k": round(sum(m["precision_at_k"] for m in per_query) / n, 4),
        "r_at_k": round(sum(m["recall_at_k"] for m in per_query) / n, 4),
        "mrr": round(sum(m["mrr"] for m in per_query) / n, 4),
        "zero_recall_queries": [m["id"] for m in per_query if not m["hit"]],
    }
    return {
        "aggregate": agg,
        "per_query": per_query,
        "n": len(per_query),
        "channel_errors": channel_errors,
    }


def _check_relevant_paths(conn, queries, verbose=True) -> list:
    """Cảnh báo `relevant` trỏ tới path không có trong DB → số liệu sẽ sai lệch."""
    known = {norm_path(r["path"]) for r in conn.execute("SELECT path FROM pages").fetchall()}
    problems = []
    for item in queries:
        for p in item["relevant"]:
            if norm_path(p) not in known:
                problems.append((item["id"], p))
    if problems and verbose:
        print("[warn] relevant path KHÔNG khớp page nào trong DB (sửa golden.toml):")
        for qid, p in problems:
            print(f"  {qid}: {p}")
    return problems


def _vector_available() -> bool:
    d = search.rag_index_dir()
    return os.path.exists(os.path.join(d, "vectors.npy")) and os.path.exists(
        os.path.join(d, "chunks.json")
    )


def _embed_model(cfg: dict) -> str:
    r = cfg.get("retrieval", {})
    return str(
        effective(
            "WIKI_EMBED_MODEL",
            (r.get("index") or {}).get("embed_model") or None,
            DEFAULT_MODEL,
        )
    )


def _make_provider(cfg: dict):
    """EmbedProvider cho wiki này, hoặc None nếu model không load được."""
    try:
        return EmbedProvider(model=_embed_model(cfg))
    except Exception as e:
        print(f"[warn] không tạo được embed provider ({e}) → bỏ kênh vector")
        return None


def _table(rows, headers):
    """Bảng tự kẻ bằng print — base venv không có `rich` (đó là dep của CLI)."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    out = [fmt.format(*headers), fmt.format(*["-" * w for w in widths])]
    out += [fmt.format(*[str(c) for c in row]) for row in rows]
    return "\n".join(out)


def _config_fingerprint(cfg: dict, base_settings: dict, golden_file: str) -> dict:
    h = ""
    try:
        with open(golden_file, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        pass
    return {
        "fusion": base_settings["fusion"],
        "chunk_bm25": base_settings["chunk_bm25"],
        "vector": base_settings["vector"],
        "rerank": base_settings.get("rerank"),
        "embed_model": _embed_model(cfg),
        "chunk_tokens": base_settings["chunk_tokens"],
        "k": base_settings.get("_k"),
        "golden_hash": h,
        "pages": base_settings.get("_pages"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Đo chất lượng retrieval trên bộ query vàng (P@k/R@k/MRR)"
    )
    ap.add_argument("--k", type=int, default=0, help="Cutoff (mặc định [eval].k, rồi top_n_final)")
    ap.add_argument("--compare", action="store_true",
                    help="So sánh tier1-weighted / rrf-text / rrf+vector")
    ap.add_argument("--json", action="store_true", dest="as_json", help="In JSON thay vì bảng")
    ap.add_argument("--init", action="store_true", help="Tạo eval/golden.toml từ template")
    ap.add_argument("--no-save", action="store_true", help="Không append vào eval/results.json")
    ap.add_argument("-v", "--verbose", action="store_true", help="In số liệu từng query")
    args = ap.parse_args()

    cfg = get_config(WIKI_ROOT)
    if args.init:
        return cmd_init(cfg)

    conn = db.get_conn()
    db.init_db(conn)
    pages = conn.execute("SELECT count(*) AS n FROM pages").fetchone()["n"]
    chunks = search.chunk_count(conn)
    golden_file = _golden_path(cfg)
    queries, errors = load_golden(golden_file)
    if not queries:
        print("Không có query vàng nào:")
        for e in errors:
            print(f"  - {e}")
        print(f"  Sửa/tạo: {golden_file}  (hoặc chạy `llm-wiki eval --init`)")
        print("  Eval cần query THẬT — không tự bịa số liệu.")
        return 0
    for e in errors:
        print(f"[warn] {e}")

    base_settings = search._retrieval_settings()
    eval_cfg = cfg.get("eval") or {}
    k = args.k or int(eval_cfg.get("k") or base_settings["top_n_final"] or 8)
    print(f"wiki={WIKI_ROOT}  pages={pages}  chunks={chunks}  k={k}  queries={len(queries)}")
    if chunks == 0 and base_settings["chunk_bm25"]:
        print("[warn] chunks_fts rỗng → kênh bm25_chunk đang tắt; "
              "chạy `llm-wiki reindex --full` rồi đo lại")
    _check_relevant_paths(conn, queries, verbose=True)

    provider = None
    runs = []

    def _with_vector(s):
        """Đảm bảo có provider trước khi bật kênh vector; không có thì tắt lại."""
        nonlocal provider
        if not s.get("vector"):
            return True
        if provider is None:
            provider = _make_provider(cfg)
        s["vector"] = provider is not None
        return s["vector"]

    if args.compare:
        for name, overrides in PROFILES:
            s = dict(base_settings)
            s.update(overrides)
            if overrides.get("vector") and not _vector_available():
                print(f"[{name}] SKIPPED — chưa có rag index "
                      "(`vector = true` + `llm-wiki reindex --full` rồi đo lại)")
                continue
            _with_vector(s)
            r = evaluate_profile(conn, queries, provider, s, k)
            r["profile"] = name
            r["settings"] = {kk: s[kk] for kk in ("fusion", "chunk_bm25", "vector", "mode")}
            runs.append(r)
    else:
        _with_vector(base_settings)
        r = evaluate_profile(conn, queries, provider, base_settings, k)
        r["profile"] = f"current({base_settings['fusion']})"
        r["settings"] = {kk: base_settings[kk] for kk in ("fusion", "chunk_bm25", "vector", "mode")}
        runs.append(r)

    if not runs:
        print("Không profile nào đo được.")
        return 0

    # Kênh chết vì lỗi = số liệu của profile đó KHÔNG đo đúng cái nó tên gọi.
    dead = {r["profile"]: r["channel_errors"] for r in runs if r["channel_errors"]}
    if dead:
        print("\n[ERROR] kênh bị tắt vì lỗi — số liệu các profile dưới đây không đủ:")
        for name, errs in dead.items():
            for ch, msg in errs.items():
                print(f"  {name}/{ch}: {msg}")

    base_fp = _config_fingerprint(cfg, dict(base_settings, _k=k, _pages=pages), golden_file)
    if args.verbose:
        for r in runs:
            print(f"\n--- {r['profile']} ---")
            for m in r["per_query"]:
                hit = "✓" if m["hit"] else "·"
                rank = m["first_hit_rank"] or "-"
                print(f"  {hit} {m['id']:<6} P@{k}={m['precision_at_k']:<6} "
                      f"R@{k}={m['recall_at_k']:<6} MRR={m['mrr']:<6} first_hit={rank}")
    if not args.as_json:
        rows = [
            [
                r["profile"],
                r["n"],
                r["aggregate"]["p_at_k"],
                r["aggregate"]["r_at_k"],
                r["aggregate"]["mrr"],
                len(r["aggregate"]["zero_recall_queries"]),
            ]
            for r in runs
        ]
        print()
        print(_table(rows, ["profile", "N", f"P@{k}", f"R@{k}", "MRR", "miss"]))
        _verdict(runs, k)

    _save_results(_results_path(cfg), runs, base_fp, k, not args.no_save)
    return 0


def _verdict(runs: list, k: int) -> None:
    """Kết luận ngắn — đúng cái roadmap cần: có bằng chứng để bật vector chưa."""
    if len(runs) < 2:
        return
    base = runs[0]["aggregate"]
    print()
    for r in runs[1:]:
        a = r["aggregate"]
        dr = round(a["r_at_k"] - base["r_at_k"], 4)
        dm = round(a["mrr"] - base["mrr"], 4)
        print(f"  Δ {r['profile']} so với {runs[0]['profile']}: R@{k} {dr:+}  MRR {dm:+}")
    vec = next((r for r in runs if r["settings"]["vector"]), None)
    if vec is None:
        print("  → chưa đo được kênh vector: `vector = true` + `llm-wiki reindex --full`")
        return
    base = runs[0]["aggregate"]
    if vec["aggregate"]["r_at_k"] > base["r_at_k"] + 0.02:
        print("  → vector cải thiện recall: cân nhắc đặt `vector = true` trong .llm-wiki.toml")
    else:
        print("  → vector KHÔNG cải thiện recall rõ rệt: giữ `vector = false` (đỡ dep, đỡ chậm)")


def _save_results(path: str, runs: list, fingerprint: dict, k: int, save: bool) -> None:
    from datetime import datetime

    entry = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "k": k,
        "config": fingerprint,
        "runs": [
            {"profile": r["profile"], "settings": r["settings"],
             "n": r["n"], "channel_errors": r["channel_errors"], **r["aggregate"]}
            for r in runs
        ],
    }
    history = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                history = json.load(f)
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    history.append(entry)
    if not save:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history[-200:], f, ensure_ascii=False, indent=2)  # giữ 200 lần cuối
    print(f"\nđã ghi {path} ({len(history)} lần đo)")


if __name__ == "__main__":
    sys.exit(main())
