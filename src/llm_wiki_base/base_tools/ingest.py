import os
import sys

import db
import search
from chunking import TRANSLATED_SUFFIX_RE, is_reserved
from config_file import effective, get_config
from embed import DEFAULT_MODEL, EmbedProvider

# Skip translated files (song song EN source + bản dịch, bản dịch KHÔNG index).
# Regex dùng chung với reindex/watch/chunk index (tools/chunking.py).


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
        print(f"skip: {full} là bản dịch (match *.lang.md), không index. Chạy llm-wiki-base translate add để tạo bản dịch.")
        sys.exit(0)
    with open(full, encoding="utf-8") as f:
        content = f.read()
    rel = os.path.relpath(full, root)
    if rel.replace(os.sep, "/").startswith("wiki/") and is_reserved(rel):
        print(f"skip: {full} là file hạ tầng (index.md/log.md), không index.")
        sys.exit(0)
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
