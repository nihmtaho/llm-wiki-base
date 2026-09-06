import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

WIKI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    if len(sys.argv) < 2:
        print("usage: python scripts/extract_youtube.py <url-or-id> [title]")
        sys.exit(1)
    vid = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else vid
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("thiếu youtube-transcript-api: pip install -r scripts/requirements.txt")
        sys.exit(1)
    if "youtu" in vid:
        import re

        m = re.search(r"(?:v=|/)([\w-]{11})", vid)
        vid = m.group(1) if m else vid
    t = YouTubeTranscriptApi.get_transcript(vid)
    text = "\n".join(f"[{round(float(s['start']), 1)}s] {s['text']}" for s in t)
    common.set_root(WIKI_ROOT)
    rel = common.save_source(title, text, ext="md", subdir="inbox")
    print(f"saved {rel} ({len(text)} chars) — chờ watch ingest")


if __name__ == "__main__":
    main()
