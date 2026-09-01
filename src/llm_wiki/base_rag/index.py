import os
import re
import json
import glob
import sys

import numpy as np
from embeddings import EmbedProvider

# Allow running as `python rag/index.py` from repo root: add parent for paths.py import.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from paths import WIKI_ROOT, WIKI_DIR, RAG_INDEX_DIR, SKIP_DIRS  # noqa: E402

# Skip bản dịch khi build chunk index (song song EN source, bản dịch KHÔNG embed).
TRANSLATED_SUFFIX_RE = re.compile(r"\.[a-z]{2,3}\.md$")

INDEX_DIR = str(RAG_INDEX_DIR)
VECTORS_FILE = os.path.join(INDEX_DIR, "vectors.npy")
CHUNKS_FILE = os.path.join(INDEX_DIR, "chunks.json")


def _chunk_markdown(text, max_chars=1200):
    """Chia theo heading, giữ context heading cha. Bỏ chunk quá ngắn."""
    chunks = []
    lines = text.split("\n")
    buf = []
    cur_heading = ""
    for line in lines:
        if line.startswith("#"):
            if buf:
                chunk = (cur_heading + "\n" + "\n".join(buf)).strip()
                if len(chunk) > 80:
                    chunks.append(chunk)
                buf = []
            cur_heading = line
        else:
            buf.append(line)
    if buf:
        chunk = (cur_heading + "\n" + "\n".join(buf)).strip()
        if len(chunk) > 80:
            chunks.append(chunk)
    # nếu file không có heading, chunk theo đoạn
    if not chunks:
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if len(para) > 80:
                chunks.append(para)
    return chunks


def build_index():
    os.makedirs(INDEX_DIR, exist_ok=True)
    files = glob.glob(os.path.join(WIKI_DIR, "**", "*.md"), recursive=True)
    chunks_meta = []
    for fp in files:
        rel = os.path.relpath(fp, WIKI_ROOT)
        parts = rel.split(os.sep)
        if any(s in SKIP_DIRS for s in parts):
            continue
        if TRANSLATED_SUFFIX_RE.search(os.path.basename(fp)):
            # bản dịch (.lang.md) — KHÔNG embed
            continue
        with open(fp, encoding="utf-8") as f:
            text = f.read()
        for i, c in enumerate(_chunk_markdown(text)):
            chunks_meta.append({"path": rel, "chunk": i, "text": c})
    prov = EmbedProvider()
    vecs = prov.embed([c["text"] for c in chunks_meta])
    arr = np.array(vecs, dtype="float32")
    np.save(VECTORS_FILE, arr)
    with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks_meta, f, ensure_ascii=False)
    return len(chunks_meta)


if __name__ == "__main__":
    n = build_index()
    print(f"indexed {n} chunks -> {INDEX_DIR}")
