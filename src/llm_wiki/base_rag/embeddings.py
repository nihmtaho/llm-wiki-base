import os
import sys

# rag/ sits next to tools/; insert tools/ onto path so `from embed import …` works
# regardless of whether the entry point was `python rag/embeddings.py` or
# `PYTHONPATH=tools python -c "from rag.embeddings import ..."`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from embed import EmbedProvider  # reuse single source of truth

__all__ = ["EmbedProvider"]
