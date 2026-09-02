import os
import re
import sys
import json
import time
import glob
import datetime

import db
import search
import lint as lintmod
from chunking import TRANSLATED_SUFFIX_RE
from config_file import get_config
from embed import EmbedProvider
from paths import WIKI_ROOT, RAW_INBOX, RAG_DIR, RAW_DIR, WIKI_DIR, WIKI_LOG_FILE, SKIP_DIRS

# Regex dùng chung với ingest/reindex/chunk index (tools/chunking.py).

WIKI_ROOT = str(WIKI_ROOT)
RAW_INBOX = str(RAW_INBOX)
RAG_DIR = str(RAG_DIR)
# Per-wiki RAG_DIR chỉ chứa .rag_index/ data, KHÔNG có code.
# Load rag code từ global base (LLM_WIKI_BASE_DIR).
_BASE_DIR = os.environ.get("LLM_WIKI_BASE_DIR") or os.path.expanduser("~/.llm-wiki-base")
_GLOBAL_RAG = os.path.join(_BASE_DIR, "rag")
if _GLOBAL_RAG not in sys.path:
    sys.path.insert(0, _GLOBAL_RAG)


def rebuild_rag():
    """Build lại rag/.rag_index/ (chunk-level) để semantic_search luôn tươi như wiki_search."""
    try:
        import index as rag_index

        return rag_index.build_index()
    except Exception as e:
        print(f"[rag] error: {e}", flush=True)
        return 0


def _conn():
    c = db.get_conn()
    db.init_db(c)
    return c


def _has_url_source(filepath):
    """Check if file has a URL in its frontmatter `source` field."""
    try:
        with open(filepath, encoding="utf-8") as f:
            in_frontmatter = False
            for line in f:
                if line.strip() == "---":
                    if in_frontmatter:
                        break
                    in_frontmatter = True
                    continue
                if in_frontmatter and line.startswith("source:"):
                    val = line.split("source:", 1)[1].strip().strip('"').strip("'")
                    return val.startswith("http://") or val.startswith("https://")
    except Exception:
        pass
    return False


def scan_ingest(c, prov):
    """Move file từ raw/inbox/ → raw/ (cả URL + no-URL).

    raw/ là local cache (gitignored mặc định, có thể xoá an toàn).
    Provenance chính nằm trong `sources:` frontmatter của wiki page:
    - URL gốc (nếu có) — strong, re-fetch được khi raw/ bị xoá.
    - `[]` (no-URL) — yếu hơn, chỉ có wiki/log.md làm witness.
    `sources:` KHÔNG cite path local trong raw/ (xem lint rule
    `sources-no-local-path` cho raw/inbox/, nhưng raw/ (ngoài inbox)
    có thể cite vì user tự quyết việc commit/backup).
    """
    if not os.path.isdir(RAW_INBOX):
        return []
    done = []
    for name in os.listdir(RAW_INBOX):
        full = os.path.join(RAW_INBOX, name)
        if not os.path.isfile(full) or name.startswith("."):
            continue
        search.index_file_at(c, full, prov)
        n = os.path.getsize(full)
        # Cả URL + no-URL đều vào raw/. Phân biệt provenance chỉ trong sources:.
        dest = os.path.join(RAW_DIR, name)
        try:
            os.replace(full, dest)
        except OSError:
            pass
        done.append((os.path.relpath(full, WIKI_ROOT), n))
    return done


def scan_wiki(c, prov):
    """Reindex wiki pages có mtime đổi → giữ DB (wiki_search) đồng bộ với wiki."""
    changed = []
    for fp in glob.glob(os.path.join(WIKI_ROOT, "wiki", "**", "*.md"), recursive=True):
        parts = os.path.relpath(fp, WIKI_ROOT).split(os.sep)
        if any(s in SKIP_DIRS for s in parts) or parts[-1].startswith("."):
            continue
        if TRANSLATED_SUFFIX_RE.search(os.path.basename(fp)):
            # bản dịch (.lang.md) — KHÔNG index
            continue
        rel = os.path.relpath(fp, WIKI_ROOT)
        mtime = os.path.getmtime(fp)
        row = c.execute("SELECT mtime FROM pages WHERE path = ?", (rel,)).fetchone()
        if row and abs(row["mtime"] - mtime) < 1e-6:
            continue
        search.index_file_at(c, fp, prov)
        changed.append(rel)
    return changed


def run_lint(c):
    return lintmod.lint(c)


def _review_due_msg():
    """Trả message nếu review (skill) quá cadence [review].interval_days, None nếu chưa đến hạn."""
    try:
        cfg = get_config(WIKI_ROOT)
        interval = int(cfg["review"].get("interval_days", 7))
        if interval <= 0:
            return None
        state_fp = os.path.join(str(WIKI_ROOT), "wiki", ".review_state.json")
        if not os.path.exists(state_fp):
            return None
        with open(state_fp, encoding="utf-8") as f:
            last = json.load(f).get("last_run")
        if not last:
            return None
        last_dt = datetime.datetime.fromisoformat(last)
        if (datetime.datetime.now() - last_dt).days >= interval:
            return f"overdue (>={interval} days, last run: {last})"
    except Exception:
        return None
    return None


def main():
    ingest_every = int(os.environ.get("WATCH_INGEST_SEC", "15"))
    lint_every = int(os.environ.get("WATCH_LINT_SEC", "3600"))
    reindex_every = int(os.environ.get("WATCH_REINDEX_SEC", "300"))
    rag_every = int(os.environ.get("WATCH_RAG_SEC", "600"))
    cfg = get_config(WIKI_ROOT)
    _r = cfg["retrieval"]
    vector_on = bool(_r.get("vector", False))
    if vector_on:
        from config_file import effective
        from embed import DEFAULT_MODEL

        _model = str(
            effective(
                "WIKI_EMBED_MODEL",
                (_r.get("index") or {}).get("embed_model") or None,
                DEFAULT_MODEL,
            )
        )
        prov = EmbedProvider(model=_model)
    else:
        prov = None
    c = _conn()
    print(
        f"[watch] inbox={RAW_INBOX} ingest={ingest_every}s reindex_wiki={reindex_every}s rag={rag_every}s lint={lint_every}s",
        flush=True,
    )
    last_lint = 0.0
    last_reindex = 0.0
    last_rag = 0.0
    while True:
        try:
            done = scan_ingest(c, prov)
            for rel, n in done:
                print(f"[ingest] {rel} ({n} chars)", flush=True)
                _insert_log(rel)
            now = time.time()
            if now - last_reindex >= reindex_every:
                ch = scan_wiki(c, prov)
                if ch:
                    print(f"[reindex] wiki pages updated: {len(ch)}", flush=True)
                last_reindex = now
            if now - last_rag >= rag_every:
                n = rebuild_rag()
                print(f"[rag] rebuilt {n} chunks", flush=True)
                last_rag = now
            if now - last_lint >= lint_every:
                rep = run_lint(c)
                print(
                    f"[lint] pages={rep['page_count']} orphans={len(rep['orphans'])} missing={len(rep['missing_file'])}",
                    flush=True,
                )
                due = _review_due_msg()
                if due:
                    print(f"[review] due — {due}", flush=True)
                last_lint = now
        except Exception as e:
            print(f"[watch] error: {e}", flush=True)
        time.sleep(ingest_every)


def _insert_log(rel):
    import re
    log = str(WIKI_LOG_FILE)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = f"## [{stamp}] ingest | {rel}\n"
    with open(log, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines(keepends=True)
    pat = re.compile(r"^## \[(\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?)\]")
    insert_at = len(lines)
    for i, ln in enumerate(lines):
        m = pat.match(ln)
        if m and m.group(1) < stamp:
            insert_at = i
            break
    lines.insert(insert_at, block)
    with open(log, "w", encoding="utf-8") as f:
        f.writelines(lines)


if __name__ == "__main__":
    main()
