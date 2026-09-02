r"""Semantic chunker thuần — KHÔNG có dependency (chỉ `re`).

Dùng chung bởi 2 pipeline index:
  - `tools/search.py`  → chunk-level BM25 (bảng `chunks_fts` trong SQLite)
  - `rag/index.py`     → chunk-level vector (`rag/.rag_index/{chunks.json,vectors.npy}`)

Lý do tách ra file riêng: chunk của BM25 và chunk của vector PHẢI cùng ranh
giới, nếu không RRF fusion giữa 2 kênh là vô nghĩa. `rag/index.py` import
numpy + fastembed ở top-level và return sớm khi `retrieval.vector=false`, nên
không thể đặt chunker ở đó — BM25 chunk-level phải chạy được khi vector tắt.

Layout: file này nằm ở `src/llm_wiki/base_tools/chunking.py` (src layout) và
`~/.llm-wiki-base/tools/chunking.py` (deployed). `rag/index.py` đã sẵn có
sys.path bootstrap chèn thư mục `tools`/`base_tools`.
"""
import os
import re

# Bản dịch (.slug.<lang>.md) KHÔNG vào bất kỳ index nào (BM25 lẫn vector).
TRANSLATED_SUFFIX_RE = re.compile(r"\.[a-z]{2,3}\.md$")

# Frontmatter block ở đầu file.
FM_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

# Dòng footnote definition: `[^id]: bằng chứng...`
FOOTNOTE_DEF_RE = re.compile(r"^\[\^[^\]]+\]\s*:")

# Tên file reserved (OKF §3) — là hạ tầng điều hướng/lịch sử, KHÔNG phải concept.
# Không chunk: log.md append-only nên mỗi entry thành 1 chunk, sẽ áp đảo
# chunk-level BM25; và watch.py reindex theo mtime → re-chunk mỗi lần ingest.
RESERVED_NAMES = frozenset({"index.md", "log.md", "readme.md"})


def is_reserved(rel: str) -> bool:
    """True nếu đây là file reserved (index.md / log.md) — không phải concept."""
    return os.path.basename(rel).lower() in RESERVED_NAMES


def is_translated(rel: str) -> bool:
    """True nếu file là bản dịch (match `*.lang.md`)."""
    return bool(TRANSLATED_SUFFIX_RE.search(os.path.basename(rel)))


def clean_body(text: str) -> str:
    """Bỏ frontmatter + dòng footnote definition khỏi chunk index.

    Footnote/bằng chứng verbatim và frontmatter thô không tốn recall budget.
    """
    text = FM_RE.sub("", text, count=1)
    lines = [ln for ln in text.split("\n") if not FOOTNOTE_DEF_RE.match(ln)]
    return "\n".join(lines)


def split_long(chunk: str, max_chars: int) -> list:
    """Cắt chunk quá dài theo ranh giới đoạn văn."""
    if len(chunk) <= max_chars:
        return [chunk]
    out = []
    buf = ""
    for para in re.split(r"\n\s*\n", chunk):
        cand = (buf + "\n\n" + para).strip() if buf else para
        if buf and len(cand) > max_chars:
            out.append(buf)
            buf = para
        else:
            buf = cand
    if buf:
        out.append(buf)
    return out or [chunk[:max_chars]]


def chunk_markdown(text: str, max_chars: int = 2048) -> list:
    """Chia theo heading, giữ context heading cha. Bỏ chunk quá ngắn.

    `max_chars` = `retrieval.chunk_tokens * 4` (xấp xỉ 4 char/token).
    """
    text = clean_body(text)
    chunks = []
    lines = text.split("\n")
    buf = []
    cur_heading = ""

    def flush():
        nonlocal buf
        if buf:
            chunk = (cur_heading + "\n" + "\n".join(buf)).strip()
            if len(chunk) > 80:
                chunks.extend(split_long(chunk, max_chars))
            buf = []

    for line in lines:
        if line.startswith("#"):
            flush()
            cur_heading = line
        else:
            buf.append(line)
    flush()
    # nếu file không có heading, chunk theo đoạn
    if not chunks:
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if len(para) > 80:
                chunks.extend(split_long(para, max_chars))
    return chunks
