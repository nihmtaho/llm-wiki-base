import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

WIKI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    if len(sys.argv) < 2:
        print("usage: python scripts/extract_url.py <url> [title]")
        sys.exit(1)
    url = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else url
    try:
        import trafilatura
    except ImportError:
        print("thiếu trafilatura: pip install -r scripts/requirements.txt")
        sys.exit(1)
    raw = trafilatura.fetch_url(url)
    text = trafilatura.extract(raw) or ""
    if not text:
        print("extract thất bại")
        sys.exit(1)
    common.set_root(WIKI_ROOT)
    rel = common.save_source(title, text, ext="md", subdir="inbox")
    print(f"saved {rel} ({len(text)} chars) — chờ watch ingest")


if __name__ == "__main__":
    main()
