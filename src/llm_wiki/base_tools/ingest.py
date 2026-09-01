import re
import sys
import os

import db
import search
from config_file import get_config, effective
from embed import EmbedProvider, DEFAULT_MODEL

# Skip translated files (song song EN source + bản dịch, bản dịch KHÔNG index).
# Match <slug>.<lang>.md pattern (lang 2-3 chữ cái). Source EN không match.
TRANSLATED_SUFFIX_RE = re.compile(r"\.[a-z]{2,3}\.md$")


def main():
    if len(sys.argv) < 2:
        print("usage: python tools/ingest.py <path-to-source>")
        sys.exit(1)
    path = sys.argv[1]
    root = db.WIKI_ROOT
    full = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.exists(full):
        print(f"not found: {full}")
        sys.exit(1)
    if TRANSLATED_SUFFIX_RE.search(os.path.basename(full)):
        print(f"skip: {full} là bản dịch (match *.lang.md), không index. Chạy llm-wiki translate add để tạo bản dịch.")
        sys.exit(0)
    with open(full, encoding="utf-8") as f:
        content = f.read()
    rel = os.path.relpath(full, root)
    domain, kind = db.extract_domain_kind(content, rel)
    title = search._title_from_content(content, rel)
    c = db.get_conn()
    db.init_db(c)
    cfg = get_config(root)
    _r = cfg["retrieval"]
    prov = None
    if _r.get("vector"):
        prov = EmbedProvider(
            model=str(
                effective(
                    "WIKI_EMBED_MODEL",
                    (_r.get("index") or {}).get("embed_model") or None,
                    DEFAULT_MODEL,
                )
            )
        )
    search.index_file(c, rel, title, domain, kind, content, provider=prov)
    print(
        f"indexed {rel} (domain={domain!r}, kind={kind!r}, {len(content)} chars) into {db.DB_PATH}"
    )


if __name__ == "__main__":
    main()
