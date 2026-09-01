"""Reindex search DB + RAG index — TĂNG DẦN theo content-hash.

Markdown là nguồn sự thật; index (DB + RAG) là derived, vứt đi rebuild được.

Chế độ:
    reindex            — tăng dần (mặc định): chỉ xử lý file đổi/mới/xoá.
    reindex --full     — rebuild toàn bộ từ đầu (bỏ qua hash). Bắt buộc sau khi
                         đổi embed_model/chunk_tokens/vector trong .llm-wiki.toml.
    reindex --check    — dry-run: báo sẽ index/xoá gì + config drift, KHÔNG ghi.

Metadata drift: <WIKI_DIR>/.index_meta.json ghi embed_model/vector/chunk_tokens
của lần reindex cuối — lệch config hiện tại → warning "chạy reindex --full".
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

import db
import search
from config_file import get_config, effective
from embed import EmbedProvider, DEFAULT_MODEL
from paths import WIKI_ROOT, WIKI_DIR, RAW_DIR, RAG_DIR, SKIP_DIRS

# Skip bản dịch khi reindex (song song EN source, bản dịch KHÔNG vào DB).
TRANSLATED_SUFFIX_RE = re.compile(r"\.[a-z]{2,3}\.md$")

# Load rag.index từ global base (RAG_DIR ở per-wiki chỉ chứa .rag_index/ data,
# KHÔNG có code). Global base path derive từ LLM_WIKI_BASE_DIR hoặc default.
_BASE_DIR = os.environ.get("LLM_WIKI_BASE_DIR") or os.path.expanduser("~/.llm-wiki-base")
_GLOBAL_RAG = os.path.join(_BASE_DIR, "rag")
if _GLOBAL_RAG not in sys.path:
    sys.path.insert(0, _GLOBAL_RAG)
import index as rag_index

INDEX_META_FILE = os.path.join(str(WIKI_DIR), ".index_meta.json")
SCHEMA_VERSION = 2


def _current_settings() -> dict:
    cfg = get_config(WIKI_ROOT)
    r = cfg["retrieval"]
    model = str(
        effective(
            "WIKI_EMBED_MODEL",
            (r.get("index") or {}).get("embed_model") or None,
            DEFAULT_MODEL,
        )
    )
    return {
        "embed_model": model,
        "vector": bool(r.get("vector", False)),
        "chunk_tokens": int(r.get("chunk_tokens", 512)),
        "schema_version": SCHEMA_VERSION,
    }


def _load_meta() -> dict:
    if os.path.exists(INDEX_META_FILE):
        try:
            with open(INDEX_META_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _collect_files() -> list[tuple[str, str]]:
    files = []
    for pat in (
        os.path.join(RAW_DIR, "**", "*.md"),
        os.path.join(WIKI_DIR, "**", "*.md"),
    ):
        for fp in glob.glob(pat, recursive=True):
            parts = os.path.relpath(fp, WIKI_ROOT).split(os.sep)
            if any(s in SKIP_DIRS for s in parts) or parts[-1].startswith("."):
                continue
            if TRANSLATED_SUFFIX_RE.search(os.path.basename(fp)):
                # bản dịch (.lang.md) — KHÔNG index
                continue
            files.append((os.path.relpath(fp, WIKI_ROOT), fp))
    return files


def _file_hash(fp: str) -> str:
    with open(fp, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _drift(meta: dict, current: dict) -> dict:
    return {
        k: {"meta": meta.get(k), "current": v}
        for k, v in current.items()
        if meta.get(k) != v
    }


def main():
    ap = argparse.ArgumentParser(
        description="Reindex search DB + RAG index (tăng dần theo content-hash)"
    )
    ap.add_argument(
        "--full", action="store_true",
        help="Rebuild toàn bộ (bỏ qua content-hash). Bắt buộc sau khi đổi embed_model/chunk_tokens/vector.",
    )
    ap.add_argument(
        "--check", action="store_true",
        help="Dry-run: báo sẽ index/xoá gì + config drift, không ghi.",
    )
    args = ap.parse_args()

    c = db.get_conn()
    db.init_db(c)
    current = _current_settings()
    meta = _load_meta()
    drift = _drift(meta, current) if meta else {}

    files = _collect_files()
    file_set = {rel for rel, _ in files}

    to_index = []
    for rel, fp in files:
        if args.full:
            to_index.append((rel, fp))
            continue
        row = c.execute(
            "SELECT content_hash FROM pages WHERE path=?", (rel,)
        ).fetchone()
        if row and row["content_hash"] and row["content_hash"] == _file_hash(fp):
            continue
        to_index.append((rel, fp))

    stale = [
        row["path"]
        for row in c.execute("SELECT path FROM pages").fetchall()
        if row["path"] not in file_set
    ]

    if args.check:
        print(f"[check] sẽ index: {len(to_index)} file(s)")
        for rel, _ in to_index[:20]:
            print(f"  + {rel}")
        if len(to_index) > 20:
            print(f"  ... và {len(to_index) - 20} file khác")
        print(f"[check] sẽ xoá stale rows: {len(stale)}")
        for p in stale[:20]:
            print(f"  - {p}")
        if drift:
            print("[check] config drift (chạy `reindex --full` để rebuild):")
            for k, d in drift.items():
                print(f"  {k}: {d['meta']} -> {d['current']}")
        return

    prov = EmbedProvider(model=current["embed_model"]) if current["vector"] else None
    n = 0
    for rel, fp in to_index:
        search.index_file_at(c, fp, prov)
        n += 1
    for p in stale:
        c.execute("DELETE FROM pages WHERE path=?", (p,))
    c.commit()
    print(f"wiki DB reindexed: {n} files indexed, removed {len(stale)} stale entries")

    with open(INDEX_META_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)

    if drift:
        print(
            "[warn] config đổi so với lần reindex trước — "
            "chạy `llm-wiki reindex --full` để rebuild embeddings theo config mới"
        )

    if not current["vector"]:
        print("vector skipped (retrieval.vector=false) — BM25/FTS vẫn chạy")
        return
    r = rag_index.build_index(full=args.full)
    print(f"rag index rebuilt: {r} chunks")


if __name__ == "__main__":
    main()
