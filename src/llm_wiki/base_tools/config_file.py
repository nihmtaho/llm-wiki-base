"""Shim — config helpers cho base tools. Re-export từ package nếu có, fallback inline copy.

tools/ chạy từ global venv (~/.llm-wiki-base/.venv) KHÔNG có package `llm_wiki`
→ fallback về bản inline dưới đây. Giữ đồng bộ phần read-only với
src/llm_wiki/config_file.py (write-only như tomli_w nằm ở package side).
"""
try:
    from llm_wiki.config_file import DEFAULTS, get_config, effective  # noqa: F401
except ImportError:
    # Fallback: chạy tools/ trực tiếp mà không cài package.
    import os
    from pathlib import Path

    try:
        import tomllib  # py3.11+
    except ImportError:  # pragma: no cover
        import tomli as tomllib  # type: ignore

    CONFIG_FILE = ".llm-wiki.toml"

    # PHẢI KHỚP KEY-FOR-KEY với llm_wiki/config_file.py DEFAULTS (bản package).
    # `llm-wiki doctor` so 2 bản và báo lỗi nếu lệch — lệch ở đây nghĩa là CLI và
    # tools/ (base venv) dùng default khác nhau cho cùng một wiki.
    DEFAULTS: dict = {
        "wiki": {
            "profile": "personal",       # personal | codebase — skill đọc key này
            "lang": "en",                # ngôn ngữ agent viết page
        },
        "translate": {
            "enabled": False,
            "langs": [],
        },
        "models": {                      # hợp đồng skill layer; Python KHÔNG gọi LLM
            "light": "",
            "heavy": "",
            "provider": "",
            "api_key_env": "",
        },
        "retrieval": {
            "mode": "hybrid",            # bm25 | hybrid
            "fusion": "rrf",             # rrf | weighted (weighted = hành vi Tier 1)
            "rrf_k": 60,
            "chunk_bm25": True,
            "vector": True,              # xem lý do + số liệu ở bản package
            "rerank": "llm",             # off | llm — skill layer đọc, Python không dùng
            "chunk_tokens": 512,
            "top_k_bm25": 20,
            "top_k_vector": 20,
            "top_n_final": 8,
            "relax_recall": True,
            "bm25_weight": 0.5,
            "vec_weight": 0.5,
            "weights": {
                "bm25_page": 1.0,
                "bm25_chunk": 1.0,
                "vector": 1.0,
            },
            "index": {
                "embed_model": "",
                "rebuild": "on-ingest",
            },
        },
        "review": {
            "interval_days": 7,
            "max_pages": 80,
        },
        "lifecycle": {
            "default_stale_after_days": 180,
        },
        "lint": {
            "banned_terms": [],
            "max_bullet_items": 3,
            "max_indent_depth": 3,
        },
        "eval": {
            "k": 8,
            "golden": "eval/golden.toml",
            "results": "eval/results.json",
        },
    }

    def _deep_merge(base: dict, override: dict) -> dict:
        out = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = _deep_merge(out[k], v)
            else:
                out[k] = v
        return out

    def get_config(wiki_root) -> dict:
        """Effective config: DEFAULTS deep-merged với `.llm-wiki.toml` (nếu có)."""
        p = Path(wiki_root) / CONFIG_FILE
        if not p.exists():
            return dict(DEFAULTS)
        with p.open("rb") as f:
            data = tomllib.load(f)
        return _deep_merge(DEFAULTS, data)

    def effective(env_name: str, toml_val, default):
        """Precedence: env > TOML > default. Env trả string (caller tự cast)."""
        env = os.environ.get(env_name)
        if env is not None and env != "":
            return env
        if toml_val is not None:
            return toml_val
        return default
