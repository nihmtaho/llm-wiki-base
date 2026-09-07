"""Legacy shim — paths moved to llm_wiki_base.paths (package). Re-export for backward compat.

Nếu package chưa cài (vd dùng tools/ trực tiếp qua PYTHONPATH=tools), fallback
về inline path logic giống bản gốc.
"""
try:
    from llm_wiki_base.paths import *  # noqa: F401,F403
except ImportError:
    # Fallback: chạy tools/ trực tiếp mà không cài package.
    import os
    from pathlib import Path
    _DEFAULT_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    def _resolve(env_name: str, default: Path) -> Path:
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
    EVAL_DIR: Path = _resolve("EVAL_DIR", WIKI_ROOT / "eval")
    SKIP_DIRS: frozenset[str] = frozenset({".proposals", ".rag_index", ".obsidian"})
