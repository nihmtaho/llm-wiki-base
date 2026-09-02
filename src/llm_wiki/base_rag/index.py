import os
import sys
import glob
import json
import hashlib
from datetime import datetime

import numpy as np
from embeddings import EmbedProvider

# Allow running as `python rag/index.py` from repo root: add tools/base_tools for paths.py import.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
sys.path.insert(0, _PARENT)
for _cand in ("tools", "base_tools"):
    _p = os.path.join(_PARENT, _cand)
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from paths import WIKI_ROOT, WIKI_DIR, RAG_INDEX_DIR, SKIP_DIRS  # noqa: E402
from config_file import get_config, effective  # noqa: E402
from embed import DEFAULT_MODEL  # noqa: E402
from chunking import (  # noqa: E402
    TRANSLATED_SUFFIX_RE,
    chunk_markdown,
    is_reserved,
)

# Chunker sống ở tools/chunking.py (dep-free) và DÙNG CHUNG với chunk-level BM25:
# 2 pipeline phải cùng ranh giới chunk thì RRF fusion giữa kênh `bm25_chunk`
# và `vector_chunk` mới có nghĩa. Alias `_chunk_markdown` giữ API cũ.
_chunk_markdown = chunk_markdown

INDEX_DIR = str(RAG_INDEX_DIR)
VECTORS_FILE = os.path.join(INDEX_DIR, "vectors.npy")
CHUNKS_FILE = os.path.join(INDEX_DIR, "chunks.json")
META_FILE = os.path.join(INDEX_DIR, "index_meta.json")


def _file_hash(fp: str) -> str:
    with open(fp, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _collect_files() -> list[tuple[str, str]]:
    files = []
    for fp in glob.glob(os.path.join(str(WIKI_DIR), "**", "*.md"), recursive=True):
        rel = os.path.relpath(fp, str(WIKI_ROOT))
        parts = rel.split(os.sep)
        if any(s in SKIP_DIRS for s in parts):
            continue
        if is_reserved(rel):
            # index.md / log.md là hạ tầng điều hướng + lịch sử, không phải concept.
            continue
        if TRANSLATED_SUFFIX_RE.search(os.path.basename(fp)):
            continue
        files.append((rel, fp))
    return files


def _load_json(fp, default):
    if os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _settings() -> dict:
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
        "vector": bool(r.get("vector", False)),
        "chunk_tokens": int(r.get("chunk_tokens", 512)),
        "embed_model": model,
    }


def build_index(full: bool = False, check: bool = False) -> int:
    """Dựng/làm mới chunk index. Tăng dần theo content-hash file.

    - File hash không đổi → giữ nguyên chunks/vectors.
    - File đổi/xoá → re-chunk + re-embed chỉ phần đó (splice vectors.npy).
    - Đổi embed_model/chunk_tokens hoặc `full=True` → rebuild từ đầu.
    - retrieval.vector=false → skip (BM25/FTS vẫn chạy qua wiki_search).
    - check=True → dry-run, không ghi.
    """
    os.makedirs(INDEX_DIR, exist_ok=True)
    s = _settings()
    if not s["vector"]:
        print("vector skipped (retrieval.vector=false)")
        return 0
    max_chars = s["chunk_tokens"] * 4

    files = _collect_files()
    fp_by_rel = dict(files)
    new_hashes = {rel: _file_hash(fp) for rel, fp in files}
    old_meta = _load_json(META_FILE, {})
    old_chunks = _load_json(CHUNKS_FILE, [])
    old_arr = None
    if os.path.exists(VECTORS_FILE):
        try:
            old_arr = np.load(VECTORS_FILE)
        except Exception:
            old_arr = None

    old_hashes = old_meta.get("file_hashes", {})
    changed = {rel for rel in new_hashes if old_hashes.get(rel) != new_hashes[rel]}
    removed = {rel for rel in old_hashes if rel not in new_hashes}
    config_changed = (
        full
        or not old_meta
        or old_meta.get("embed_model") != s["embed_model"]
        or old_meta.get("chunk_tokens") != s["chunk_tokens"]
        or old_arr is None
        or (old_arr is not None and len(old_chunks) != len(old_arr))
    )

    if check:
        mode = "config đổi → full rebuild" if config_changed else "incremental"
        print(
            f"[check] rag ({mode}): sẽ re-chunk {len(changed)} file(s), "
            f"gỡ {len(removed)} file(s), tổng {len(new_hashes)} file"
        )
        return len(old_chunks)

    prov = EmbedProvider(model=s["embed_model"])

    if config_changed:
        chunks_meta = []
        for rel, fp in files:
            with open(fp, encoding="utf-8") as f:
                text = f.read()
            for i, ch in enumerate(_chunk_markdown(text, max_chars)):
                chunks_meta.append({"path": rel, "chunk": i, "text": ch})
        if chunks_meta:
            vecs = prov.embed([c["text"] for c in chunks_meta])
            arr = np.array(vecs, dtype="float32")
        else:
            arr = np.zeros((0, 1), dtype="float32")
        print(f"rag index rebuilt (full): {len(chunks_meta)} chunks")
    else:
        drop = changed | removed
        keep_idx = [i for i, c in enumerate(old_chunks) if c["path"] not in drop]
        keep_chunks = [old_chunks[i] for i in keep_idx]
        if keep_idx:
            kept_arr = old_arr[keep_idx]
        else:
            kept_arr = np.zeros((0, old_arr.shape[1]), dtype="float32")
        new_chunks = []
        for rel in sorted(changed & set(fp_by_rel)):
            with open(fp_by_rel[rel], encoding="utf-8") as f:
                text = f.read()
            for i, ch in enumerate(_chunk_markdown(text, max_chars)):
                new_chunks.append({"path": rel, "chunk": i, "text": ch})
        if new_chunks:
            vecs = prov.embed([c["text"] for c in new_chunks])
            new_arr = np.array(vecs, dtype="float32")
            arr = np.vstack([kept_arr, new_arr]) if len(kept_arr) else new_arr
        else:
            arr = kept_arr
        chunks_meta = keep_chunks + new_chunks
        print(
            f"rag index updated: +{len(new_chunks)} chunks "
            f"(re-chunked {len(changed)} file(s), removed {len(removed)} file(s))"
        )

    np.save(VECTORS_FILE, arr)
    with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks_meta, f, ensure_ascii=False)
    meta = {
        "file_hashes": new_hashes,
        "embed_model": s["embed_model"],
        "chunk_tokens": s["chunk_tokens"],
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return len(chunks_meta)


if __name__ == "__main__":
    n = build_index()
    print(f"indexed {n} chunks -> {INDEX_DIR}")
