import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

WIKI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    if len(sys.argv) < 2:
        print("usage: python scripts/extract_pdf.py <pdf-path> [title]")
        sys.exit(1)
    pdf = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(pdf)
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("thiếu PyMuPDF: pip install -r scripts/requirements.txt")
        sys.exit(1)
    doc = fitz.open(pdf)
    text = "\n\n".join(page.get_text() for page in doc)
    doc.close()
    common.set_root(WIKI_ROOT)
    rel = common.save_source(title, text, ext="md", subdir="inbox")
    print(f"saved {rel} ({len(text)} chars) — chờ watch ingest")


if __name__ == "__main__":
    main()
