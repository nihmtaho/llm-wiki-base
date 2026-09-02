"""Read/write `.llm-wiki.toml` ở wiki root.

File này là behavior config per-wiki (commit vào wiki repo). Runtime plumbing
(paths, DB routing) vẫn qua env vars — precedence: env > TOML > builtin default.

Format:
    [translate]
    enabled = true
    langs = ["vi", "ja"]

    [retrieval]
    mode = "hybrid"
    fusion = "rrf"
    vector = false
    ...

    [retrieval.weights]     # RRF weight per kênh
    bm25_page = 1.0
    ...

Sections không có trong file lấy từ `DEFAULTS`. Writer dùng `tomli-w`
(pure-Python) để support đúng kiểu int/bool/nested table/array-of-tables.
"""
import os
from pathlib import Path
from typing import Iterable

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

import tomli_w

CONFIG_FILE = ".llm-wiki.toml"

# Defaults cho mọi section. File `.llm-wiki.toml` chỉ cần ghi đè key muốn đổi.
DEFAULTS: dict = {
    "translate": {
        "enabled": False,
        "langs": [],
    },
    "retrieval": {
        "mode": "hybrid",        # bm25 | hybrid (hybrid = thêm kênh vector khi vector=true)
        "fusion": "rrf",         # rrf | weighted  (weighted = hành vi Tier 1, để rollback/A-B)
        "rrf_k": 60,             # hằng số RRF; nhỏ hơn = ưu tiên hạng cao hơn
        "chunk_bm25": True,      # kênh BM25 trên semantic chunks (cần `reindex --full` 1 lần)
        "vector": False,         # BẬT sau khi `llm-wiki eval --compare` cho thấy recall tụt
        "rerank": "llm",         # off | llm — SKILL layer đọc, Python không dùng
        "chunk_tokens": 512,     # chunk theo section ~ chunk_tokens*4 chars (approx)
        "top_k_bm25": 20,        # số ứng viên mỗi kênh text (không phải kết quả cuối)
        "top_k_vector": 20,      # số ứng viên kênh vector
        "top_n_final": 8,        # số concept trả về cuối sau fusion
        "relax_recall": True,    # AND-match 0 kết quả -> thử lại OR một lần
        "bm25_weight": 0.5,      # chỉ chi phối khi fusion="weighted"; RRF seed cho 2 kênh text
        "vec_weight": 0.5,       # chỉ chi phối khi fusion="weighted"; RRF seed cho kênh vector
        "weights": {             # RRF weight per kênh (chỉ cần TỈ số)
            "bm25_page": 1.0,
            "bm25_chunk": 1.0,
            "vector": 1.0,
        },
        "index": {
            "embed_model": "",   # rỗng = builtin default
            "rebuild": "on-ingest",  # on-ingest | on-demand | manual
        },
    },
    "review": {
        "interval_days": 7,
        "max_pages": 80,
    },
    "lifecycle": {
        "default_stale_after_days": 180,  # 0 = không set stale_after
    },
    "lint": {
        "banned_terms": [],
        "max_bullet_items": 3,
        "max_indent_depth": 3,
    },
    "eval": {
        "k": 8,                            # cutoff mặc định của `llm-wiki eval`
        "golden": "eval/golden.toml",      # query vàng — COMMIT
        "results": "eval/results.json",    # lịch sử đo — gitignored
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


def load(wiki_root: Path) -> dict:
    """Load `.llm-wiki.toml`. Trả dict rỗng nếu file không tồn tại."""
    p = Path(wiki_root) / CONFIG_FILE
    if not p.exists():
        return {}
    with p.open("rb") as f:
        return tomllib.load(f)


def get_config(wiki_root: Path) -> dict:
    """Effective config: DEFAULTS deep-merged với `.llm-wiki.toml` (nếu có)."""
    return _deep_merge(DEFAULTS, load(wiki_root))


def effective(env_name: str, toml_val, default):
    """Precedence: env > TOML > default.

    Env luôn trả string (caller tự cast); TOML giữ kiểu từ file.
    """
    env = os.environ.get(env_name)
    if env is not None and env != "":
        return env
    if toml_val is not None:
        return toml_val
    return default


def get_translate_config(wiki_root: Path) -> tuple[bool, list[str]]:
    """Trả (enabled, langs). Default (False, [])."""
    section = get_config(wiki_root).get("translate", {})
    enabled = bool(section.get("enabled", False))
    langs = list(section.get("langs", []))
    return enabled, langs


def set_translate(wiki_root: Path, enabled: bool, langs: Iterable[str]) -> Path:
    """Ghi `.llm-wiki.toml` với `[translate]` section. Giữ các section khác nguyên.

    Returns path tới file đã ghi.
    """
    p = Path(wiki_root) / CONFIG_FILE
    data = load(wiki_root)
    data["translate"] = {
        "enabled": enabled,
        "langs": sorted(set(langs)),
    }
    _write_toml(p, data)
    return p


def _write_toml(p: Path, data: dict) -> None:
    """Ghi dict thành TOML qua tomli-w (support int/float/bool/nested/array-of-tables)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as f:
        tomli_w.dump(data, f)
