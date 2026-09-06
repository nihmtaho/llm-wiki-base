"""Central path constants for the wiki pipeline.

Mọi file trong tools/ + rag/ + scripts/ nên import từ đây thay vì tự dựng path.
Env var override đều có default dạng "relative to WIKI_ROOT" để vẫn chạy được
khi user copy repo sang máy khác / đổi tên folder.

Env vars (override):
  WIKI_ROOT         — repo root. Mặc định: parent của tools/ (cho layout tools/paths.py ở <root>/tools/).
  WIKI_DIR          — folder chứa wiki pages. Mặc định: <root>/wiki.
  WIKI_INDEX_FILE   — top-level index. Mặc định: <WIKI_DIR>/index.md.
  WIKI_LOG_FILE     — append-only log. Mặc định: <WIKI_DIR>/log.md.
  WIKI_DB_FILE      — SQLite + FTS5 search index. Mặc định: <WIKI_DIR>/.wiki.db.
  WIKI_PROPOSALS    — staging for human-gated edits. Mặc định: <WIKI_DIR>/.proposals.
  RAW_DIR           — immutable sources with URL. Mặc định: <root>/raw.
  RAW_INBOX         — staging for new sources. Mặc định: <RAW_DIR>/inbox.
  ARCHIVED_DIR      — immutable sources without URL. Mặc định: <root>/archived.
  RAG_DIR           — semantic search module. Mặc định: <root>/rag.
  RAG_INDEX_DIR     — generated chunk embeddings. Mặc định: <RAG_DIR>/.rag_index.
  EVAL_DIR          — eval harness (golden.toml + results.json). Mặc định: <root>/eval.
"""
import os
from pathlib import Path

# Repo root — derived from this file's location. For src-layout, parent of src/llm_wiki_base/paths.py
# is <root>/src/llm_wiki_base/ → go up 3 levels to reach <root>. For tools/paths.py shim,
# `__file__` is the tools/ copy and parent is <root>/tools/ → go up 1.
_this = Path(__file__).resolve()
if _this.parent.name == "llm_wiki_base" and _this.parent.parent.name == "src":
    _DEFAULT_ROOT = _this.parent.parent.parent  # .../src/llm_wiki_base/paths.py → .../
else:
    _DEFAULT_ROOT = _this.parent.parent  # .../tools/paths.py → ../


def _resolve(env_name: str, default: Path) -> Path:
    """Resolve env var (if set) or return default. Path is always absolute."""
    val = os.environ.get(env_name)
    if val:
        p = Path(val)
        return p if p.is_absolute() else (_DEFAULT_ROOT / p).resolve()
    return default


WIKI_ROOT: Path = _resolve("WIKI_ROOT", _DEFAULT_ROOT)

WIKI_DIR: Path = _resolve("WIKI_DIR", WIKI_ROOT / "wiki")
WIKI_INDEX_FILE: Path = _resolve("WIKI_INDEX_FILE", WIKI_DIR / "index.md")
WIKI_LOG_FILE: Path = _resolve("WIKI_LOG_FILE", WIKI_DIR / "log.md")
WIKI_DB_FILE: Path = _resolve("WIKI_DB_FILE", WIKI_DIR / ".wiki.db")
WIKI_PROPOSALS: Path = _resolve("WIKI_PROPOSALS", WIKI_DIR / ".proposals")

RAW_DIR: Path = _resolve("RAW_DIR", WIKI_ROOT / "raw")
RAW_INBOX: Path = _resolve("RAW_INBOX", RAW_DIR / "inbox")

RAG_DIR: Path = _resolve("RAG_DIR", WIKI_ROOT / "rag")
RAG_INDEX_DIR: Path = _resolve("RAG_INDEX_DIR", RAG_DIR / ".rag_index")

# Eval harness: golden.toml COMMIT (đây KHÔNG phải dưới wiki/ — lint coi mọi
# thư mục không-ẩn dưới wiki/ là một domain và sẽ báo domain-missing-index),
# results.json gitignored.
EVAL_DIR: Path = _resolve("EVAL_DIR", WIKI_ROOT / "eval")

# Directories inside wiki/ or other top-levels that should be SKIPPED by
# reindex/scan/lint (contain staging, generated artefacts, or hidden config).
SKIP_DIRS: frozenset[str] = frozenset({".proposals", ".rag_index", ".obsidian"})
