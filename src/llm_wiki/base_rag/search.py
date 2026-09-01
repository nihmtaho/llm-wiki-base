import os
import json
import sys
import numpy as np
from embeddings import EmbedProvider

# Allow running as `python rag/search.py` from repo root: add tools/base_tools for paths.py import.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
sys.path.insert(0, _PARENT)
for _cand in ("tools", "base_tools"):
    _p = os.path.join(_PARENT, _cand)
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from paths import RAG_INDEX_DIR, WIKI_ROOT  # noqa: E402
from config_file import get_config, effective  # noqa: E402
from embed import DEFAULT_MODEL  # noqa: E402

INDEX_DIR = str(RAG_INDEX_DIR)
VECTORS_FILE = os.path.join(INDEX_DIR, "vectors.npy")
CHUNKS_FILE = os.path.join(INDEX_DIR, "chunks.json")


def _query_provider() -> EmbedProvider:
    """Query embed model khớp model đã index (env > TOML > builtin)."""
    cfg = get_config(WIKI_ROOT)
    model = str(
        effective(
            "WIKI_EMBED_MODEL",
            (cfg["retrieval"].get("index") or {}).get("embed_model") or None,
            DEFAULT_MODEL,
        )
    )
    return EmbedProvider(model=model)


def semantic_search(query, top_k=8):
    if not os.path.exists(VECTORS_FILE):
        return {"error": "chưa build index — chạy rag/index.py"}
    arr = np.load(VECTORS_FILE)
    with open(CHUNKS_FILE, encoding="utf-8") as f:
        meta = json.load(f)
    if arr.size == 0 or not meta:
        return []
    q = np.array(_query_provider().embed([query])[0], dtype="float32")
    q /= np.linalg.norm(q) + 1e-9
    norms = np.linalg.norm(arr, axis=1) + 1e-9
    sims = (arr / norms[:, None]) @ q
    idx = sims.argsort()[::-1][:top_k]
    return [
        {
            "path": meta[i]["path"],
            "chunk": meta[i]["chunk"],
            "score": round(float(sims[i]), 4),
            "snippet": meta[i]["text"][:300],
        }
        for i in idx
    ]


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "vector search"
    print(json.dumps(semantic_search(q), ensure_ascii=False, indent=2))
