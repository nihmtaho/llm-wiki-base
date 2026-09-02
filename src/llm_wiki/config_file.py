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

Ngoại lệ: file của NGƯỜI DÙNG thì không được in lại từ dict — `tomli_w.dump` xoá
sạch comment. Mọi write vào `.llm-wiki.toml` đã tồn tại đi qua `_upsert_toml_keys`
(sửa đúng dòng của key được yêu cầu).
"""
import os
import re
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
    "wiki": {
        # profile quyết định TÍNH CHẤT nội dung skill viết ra (không phải đường dẫn).
        # `init personal` -> personal; `init project` -> codebase. Skill đọc key này
        # để biết có phải kiểm code path / tách intent-observation hay không.
        "profile": "personal",     # personal | codebase
        "lang": "en",              # ngôn ngữ agent PHẢI viết page; `translate.langs` = đích dịch
    },
    "translate": {
        "enabled": False,
        "langs": [],
    },
    "models": {
        # CHỈ LÀ HỢP ĐỒNG CHO SKILL LAYER / công cụ ngoài. Python pipeline KHÔNG gọi
        # LLM và KHÔNG đọc section này — ingest/review/translate vẫn chạy bằng LLM của
        # AI tool đang mở (`llm-wiki doctor` nhắc rõ điều đó). Có section này để:
        #  (1) khai báo model mong muốn ở một chỗ, skill đọc và theo;
        #  (2) sẵn chỗ cho headless ingest khi nào thật sự cần, không đổi format config.
        "light": "",               # WRITE: sinh concept (vd "claude-sonnet-5")
        "heavy": "",               # VERIFY/review: kiểm ngữ nghĩa (adversarial)
        "provider": "",            # openai-compatible | anthropic | ollama — rỗng = dùng LLM của AI tool
        "api_key_env": "",         # TÊN biến môi trường chứa key — KHÔNG bao giờ ghi key thẳng vào file
    },
    "retrieval": {
        "mode": "hybrid",        # bm25 | hybrid (hybrid = thêm kênh vector khi vector=true)
        "fusion": "rrf",         # rrf | weighted  (weighted = hành vi Tier 1, để rollback/A-B)
        "rrf_k": 60,             # hằng số RRF; nhỏ hơn = ưu tiên hạng cao hơn
        "chunk_bm25": True,      # kênh BM25 trên semantic chunks (cần `reindex --full` 1 lần)
        "vector": True,          # BẬT mặc định từ 2026-09-02 — đo trên wiki thật: R@8
                                 # 0.9167 -> 0.9722 và MRR 0.8518 -> 0.8981 so với text-only.
                                 # Tắt khi: máy không có fastembed/model, hoặc eval của
                                 # chính wiki đó cho thấy rrf+vector không hơn rrf-text.
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
    """Ghi `[translate].enabled` + `.langs`, GIỮ NGUYÊN comment và các section khác.

    Bản cũ parse-then-dump (`_write_toml`) → mọi comment trong `.llm-wiki.toml` bốc
    hơi, kể cả block ghi lý do bật vector. Comment ở file này là tài liệu, không phải
    trang trí — không được phá.
    """
    p = Path(wiki_root) / CONFIG_FILE
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    literal = "[" + ", ".join(f'"{x}"' for x in sorted(set(langs))) + "]"
    out = _upsert_toml_keys(text, "translate", {
        "enabled": "true" if enabled else "false",
        "langs": literal,
    })
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out, encoding="utf-8")
    return p


def ensure_wiki_identity(cfg_path: Path, profile: str,
                         lang: str | None = None) -> bool:
    """Ép `[wiki].profile` (và `lang` nếu đưa) đúng loại wiki vừa init.

    Template mang giá trị của personal; `init project` phải ra `codebase`. Skill đọc
    `[wiki].profile` để quyết định có verify code path / tách intent-observation hay
    không, nên sai key này = skill chạy nhầm chế độ.

    Returns True nếu file thay đổi. Không tạo file mới (wiki chưa có config thì
    để `config show` dùng default).
    """
    if not cfg_path.is_file():
        return False
    text = cfg_path.read_text(encoding="utf-8")
    pairs = {"profile": f'"{profile}"'}
    if lang:
        pairs["lang"] = f'"{lang}"'
    out = _upsert_toml_keys(text, "wiki", pairs)
    if out == text:
        return False
    cfg_path.write_text(out, encoding="utf-8")
    return True


def _upsert_toml_keys(text: str, section: str, pairs: dict[str, str]) -> str:
    """Sửa/thêm key trong MỘT section của TOML dạng text, không đụng phần còn lại.

    `pairs`: key → TOML literal (đã có ngoặc/chuỗi, vd '\"codebase\"', 'true',
    '[\"vi\", \"ja\"]'). Comment cuối dòng được giữ; comment của section khác không
    liên quan gì tới nhau. Đây là lý do không dùng tomli_w.dump (nó in lại cả file
    từ dict → mất trắng comment).
    """
    lines = text.splitlines() if text.strip() else []
    hdr = next((i for i, ln in enumerate(lines)
                if re.match(rf"^\s*\[{re.escape(section)}\]\s*(#.*)?$", ln)), None)

    if hdr is None:                       # section chưa tồn tại → chèn trước section đầu
        insert_at = next((i for i, ln in enumerate(lines)
                          if re.match(r"^\s*\[[a-zA-Z]", ln)), len(lines))
        block = [f"[{section}]", *(f"{k} = {v}" for k, v in pairs.items()), ""]
        lines[insert_at:insert_at] = block
        return "\n".join(lines) + "\n"

    end = next((i for i in range(hdr + 1, len(lines))
                if re.match(r"^\s*\[", lines[i])), len(lines))
    for key, val in pairs.items():
        pat = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)([^#]*?)(\s*#.*)?$")
        hit = next((i for i in range(hdr + 1, end) if pat.match(lines[i])), None)
        if hit is None:                   # key chưa có trong section → thêm cuối section
            lines.insert(end, f"{key} = {val}")
            end += 1
            continue
        m = pat.match(lines[hit])
        current, comment = m.group(2).strip(), (m.group(3) or "")
        if current != val.strip():
            lines[hit] = f"{key} = {val}{comment}"
    return "\n".join(lines) + "\n"


def _write_toml(p: Path, data: dict) -> None:
    """Ghi dict thành TOML qua tomli-w. KHÔNG dùng cho file có comment của user."""
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as f:
        tomli_w.dump(data, f)
