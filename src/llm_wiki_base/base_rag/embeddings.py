import os
import sys

# rag/ sits next to tools/ (deployed: ~/.llm-wiki-base/{rag,tools}) hoặc base_tools/
# (src layout: src/llm_wiki_base/{base_rag,base_tools}) — insert cả hai candidate để
# `from embed import …` hoạt động ở cả hai layout.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
sys.path.insert(0, _PARENT)
for _cand in ("tools", "base_tools"):
    _p = os.path.join(_PARENT, _cand)
    if os.path.isdir(_p):
        sys.path.insert(0, _p)
from embed import EmbedProvider  # noqa: E402 — reuse single source of truth

__all__ = ["EmbedProvider"]
