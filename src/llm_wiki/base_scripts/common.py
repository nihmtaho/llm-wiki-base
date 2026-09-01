import os
import re
import datetime
import unicodedata

WIKI_ROOT = None  # set by caller via set_root


def set_root(path: str):
    global WIKI_ROOT
    WIKI_ROOT = path


def slugify(text: str, max_len: int = 80) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_len].strip("-") or "source"


def save_source(title: str, content: str, ext: str = "md", subdir: str = "inbox") -> str:
    """Lưu nguồn vào raw/<subdir>/ kèm frontmatter, trả về path tương đối."""
    if WIKI_ROOT is None:
        raise RuntimeError("call set_root() first")
    out_dir = os.path.join(WIKI_ROOT, "raw", subdir)
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    name = f"{stamp}-{slugify(title)}.{ext}"
    path = os.path.join(out_dir, name)
    front = (
        f"---\ntitle: {title}\n"
        f"ingested: {datetime.datetime.now().isoformat(timespec='seconds')}\n"
        f"status: pending\n---\n\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(front + content)
    return os.path.relpath(path, WIKI_ROOT)
