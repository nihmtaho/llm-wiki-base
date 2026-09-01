import os
import re
import sys
import glob

import db
import search
from embed import EmbedProvider
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


def main():
    c = db.get_conn()
    db.init_db(c)
    prov = EmbedProvider()

    # Collect all existing files
    existing = set()
    n = 0
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
            rel = os.path.relpath(fp, WIKI_ROOT)
            existing.add(rel)
            search.index_file_at(c, fp, prov)
            n += 1

    # Delete stale entries
    stale = [row["path"] for row in c.execute("SELECT path FROM pages").fetchall() if row["path"] not in existing]
    for p in stale:
        c.execute("DELETE FROM pages WHERE path=?", (p,))
    c.commit()

    print(f"wiki DB reindexed: {n} files, removed {len(stale)} stale entries")
    r = rag_index.build_index()
    print(f"rag index rebuilt: {r} chunks")


if __name__ == "__main__":
    main()
