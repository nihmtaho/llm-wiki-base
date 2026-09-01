import json
import os
import re
import sqlite3

from paths import WIKI_ROOT, WIKI_DB_FILE

# Backwards-compat: WIKI_DB env var still wins (legacy name).
DB_PATH = os.environ.get("WIKI_DB", str(WIKI_DB_FILE))
WIKI_ROOT = str(WIKI_ROOT)  # keep as str for legacy callers (db.WIKI_ROOT)


def get_conn(db_path: str | None = None) -> sqlite3.Connection:
    """Mở SQLite connection. Nếu db_path=None dùng module default (DB_PATH từ env).

    Centralized MCP server truyền db_path tường mỗi wiki để hỗ trợ multi-wiki.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Frontmatter parser — nhẹ, không phụ thuộc PyYAML. Đủ cho wiki schema.
# ─────────────────────────────────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _split_top(s: str, sep: str) -> list[str]:
    """Split tôn trọng quote + bracket lồng (cho inline dict/list)."""
    parts: list[str] = []
    buf = ""
    quote: str | None = None
    depth = 0
    for ch in s:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf += ch
            continue
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    return parts


def _parse_inline_dict(val: str) -> dict | None:
    """Parse `{k: v, k2: "v2"}` (flat dict). Trả None nếu không phải dict hợp lệ."""
    if not (val.startswith("{") and val.endswith("}")):
        return None
    inner = val[1:-1].strip()
    if not inner:
        return {}
    out: dict = {}
    for part in _split_top(inner, ","):
        if ":" not in part:
            continue
        k, _, v = part.partition(":")
        out[k.strip().strip("\"'")] = v.strip().strip("\"'")
    return out


def parse_frontmatter(content: str) -> dict:
    """Parse YAML-like frontmatter từ đầu file markdown. Trả dict rỗng nếu không có.

    Hỗ trợ:
    - key: value (string)
    - key: [a, b, c] (inline list)
    - key: {k: v, k2: "v2"} (inline dict flat — vd generated/verified trust fields)
    - key: (block) list nhiều dòng "  - " — item là string HOẶC dict với
      continuation "    key: value" (vd sources list-of-dicts có id/resource)

    Nested sâu hơn không hỗ trợ — đủ cho schema wiki. Nếu cần YAML đầy đủ → pip install pyyaml.
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    block = m.group(1)
    out: dict = {}
    current_key: str | None = None
    current_list: list | None = None
    current_dict: dict | None = None

    def _flush_list() -> None:
        nonlocal current_key, current_list, current_dict
        if current_key is not None and current_list is not None:
            out[current_key] = current_list
        current_key = None
        current_list = None
        current_dict = None

    for raw in block.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        # dict continuation trong block list (vd "    resource: ..." sau "  - id: s1")
        if current_dict is not None and line.startswith("    ") and ":" in line:
            k, _, v = line.strip().partition(":")
            current_dict[k.strip()] = v.strip().strip("\"'")
            continue
        if current_list is not None and line.startswith("  - "):
            item = line[4:].strip()
            if ":" in item:
                k, _, v = item.partition(":")
                d = {k.strip(): v.strip().strip("\"'")}
                current_list.append(d)
                current_dict = d
            else:
                current_dict = None
                current_list.append(item)
            continue
        if current_list is not None:
            _flush_list()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not val:
            current_key = key
            current_list = []
            current_dict = None
            continue
        if val.startswith("{") and val.endswith("}"):
            d = _parse_inline_dict(val)
            out[key] = d if d is not None else val
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            out[key] = [s.strip().strip('"').strip("'") for s in inner.split(",") if s.strip()]
        else:
            out[key] = val.strip('"').strip("'")
    _flush_list()
    return out


# Legacy `category` values mapping → mặc định coi như `domain` (vì 3 folder cũ = 3 domain cũ).
LEGACY_CATEGORIES = {"tech", "projects", "languages"}


def infer_domain_kind_from_path(path: str) -> tuple[str, str]:
    """Fallback khi page không có frontmatter `domain`/`kind`.

    Path dạng: 'wiki/<top>/<inner>/<file>.md' hoặc 'wiki/<top>/<file>.md'.
    Trả (domain, kind). kind = 'index' nếu file là <domain>/index.md.

    Top-level files (wiki/index.md, wiki/log.md) — không thuộc domain nào.
    """
    parts = path.replace("\\", "/").split("/")
    if not parts or parts[0] != "wiki":
        return "", ""
    if len(parts) < 2:
        return "", ""
    # Top-level: wiki/<file>.md (vd: wiki/index.md, wiki/log.md) → no domain
    if len(parts) == 2:
        return "", ""
    domain = parts[1]
    if len(parts) == 3 and parts[2] == "index.md":
        return domain, "index"
    kind = parts[2] if len(parts) > 2 else ""
    return domain, kind


def extract_domain_kind(content: str, path: str) -> tuple[str, str]:
    """Trích domain/kind ưu tiên frontmatter, fallback infer từ path.

    Backwards-compat: nếu frontmatter có `category: tech|projects|languages` mà
    không có `domain`, dùng `category` làm domain.
    """
    fm = parse_frontmatter(content)
    domain = (fm.get("domain") or "").strip()
    kind = (fm.get("kind") or "").strip()
    if not domain and "category" in fm:
        cat = (fm.get("category") or "").strip()
        if cat in LEGACY_CATEGORIES:
            domain = cat
    if not domain or not kind:
        path_domain, path_kind = infer_domain_kind_from_path(path)
        if not domain:
            domain = path_domain
        if not kind:
            kind = path_kind
    return domain, kind


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == column for row in cur.fetchall())


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            title TEXT,
            category TEXT,
            domain TEXT DEFAULT '',
            kind TEXT DEFAULT '',
            content TEXT,
            mtime REAL,
            embedding TEXT
        )
        """
    )
    if not _table_has_column(conn, "pages", "domain"):
        conn.execute("ALTER TABLE pages ADD COLUMN domain TEXT DEFAULT ''")
    if not _table_has_column(conn, "pages", "kind"):
        conn.execute("ALTER TABLE pages ADD COLUMN kind TEXT DEFAULT ''")
    if not _table_has_column(conn, "pages", "content_hash"):
        conn.execute("ALTER TABLE pages ADD COLUMN content_hash TEXT DEFAULT ''")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pages_category ON pages(category)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pages_domain ON pages(domain)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pages_kind ON pages(kind)"
    )
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts
            USING fts5(content, title, content='pages', content_rowid='id')
            """
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()


def upsert_page(
    conn,
    path,
    title,
    domain,
    kind,
    content,
    mtime,
    embedding=None,
    category="",
    content_hash=None,
):
    """Upsert page. `category` legacy chỉ dùng cho row cũ — page mới truyền category=''."""
    emb = json.dumps(embedding) if embedding is not None else None
    cur = conn.execute("SELECT id FROM pages WHERE path = ?", (path,))
    row = cur.fetchone()
    if row:
        pid = row["id"]
        conn.execute(
            "UPDATE pages SET title=?, category=?, domain=?, kind=?, content=?, mtime=?, embedding=?, content_hash=? WHERE id=?",
            (title, category, domain, kind, content, mtime, emb, content_hash or "", pid),
        )
    else:
        cur = conn.execute(
            "INSERT INTO pages (path, title, category, domain, kind, content, mtime, embedding, content_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            (path, title, category, domain, kind, content, mtime, emb, content_hash or ""),
        )
        pid = cur.lastrowid
    conn.execute(
        "INSERT INTO pages_fts (rowid, content, title) VALUES (?,?,?)",
        (pid, content, title),
    )
    conn.commit()
    return pid


def delete_page(conn, path):
    cur = conn.execute("SELECT id FROM pages WHERE path = ?", (path,))
    row = cur.fetchone()
    if not row:
        return
    conn.execute("DELETE FROM pages_fts WHERE rowid = ?", (row["id"],))
    conn.execute("DELETE FROM pages WHERE id = ?", (row["id"],))
    conn.commit()


def list_pages(conn, domain=None, kind=None, category=None):
    """Liệt kê pages. Filter theo domain/kind (ưu tiên) hoặc category (legacy alias).

    `category` ở đây map sang `domain` cho backwards-compat (vì legacy categories
    tech|projects|languages là 1:1 với 3 domain đầu tiên).
    """
    where = []
    args: list = []
    if domain is not None:
        where.append("domain = ?")
        args.append(domain)
    elif category is not None:
        # legacy alias
        where.append("domain = ?")
        args.append(category)
    if kind is not None:
        where.append("kind = ?")
        args.append(kind)
    sql = "SELECT path, title, domain, kind, category FROM pages"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY path"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_page(conn, path):
    cur = conn.execute(
        "SELECT path, title, domain, kind, category, content, embedding FROM pages WHERE path = ?",
        (path,),
    )
    row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["embedding"] = json.loads(d["embedding"]) if d["embedding"] else None
    return d
