import os
import json
import sys
import numpy as np
from embeddings import EmbedProvider

# Allow running as `python rag/search.py` from repo root: add parent for paths.py import.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from paths import RAG_INDEX_DIR  # noqa: E402

INDEX_DIR = str(RAG_INDEX_DIR)
VECTORS_FILE = os.path.join(INDEX_DIR, "vectors.npy")
CHUNKS_FILE = os.path.join(INDEX_DIR, "chunks.json")


def semantic_search(query, top_k=8):
    if not os.path.exists(VECTORS_FILE):
        return {"error": "chưa build index — chạy rag/index.py"}
    arr = np.load(VECTORS_FILE)
    with open(CHUNKS_FILE, encoding="utf-8") as f:
        meta = json.load(f)
    q = np.array(EmbedProvider().embed([query])[0], dtype="float32")
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
