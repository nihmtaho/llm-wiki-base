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


def parse_frontmatter(content: str) -> dict:
    """Parse YAML-like frontmatter từ đầu file markdown. Trả dict rỗng nếu không có.

    Hỗ trợ:
    - key: value (string)
    - key: [a, b, c] (list)
    - key: (block) — danh sách nhiều dòng bắt đầu bằng "  - " (cho pins:)

    Không hỗ trợ nested/complex — đủ cho schema wiki. Nếu cần YAML đầy đủ → pip install pyyaml.
    """
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}
    block = m.group(1)
    out: dict = {}
    current_key: str | None = None
    current_list: list | None = None
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if current_list is not None and line.startswith("  - "):
            current_list.append(line[4:].strip())
            continue
        if current_list is not None:
            out[current_key] = current_list
            current_list = None
            current_key = None
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not val:
            current_key = key
            current_list = []
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            out[key] = [s.strip().strip('"').strip("'") for s in inner.split(",") if s.strip()]
        else:
            out[key] = val.strip('"').strip("'")
    if current_list is not None and current_key is not None:
        out[current_key] = current_list
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
):
    """Upsert page. `category` legacy chỉ dùng cho row cũ — page mới truyền category=''."""
    emb = json.dumps(embedding) if embedding is not None else None
    cur = conn.execute("SELECT id FROM pages WHERE path = ?", (path,))
    row = cur.fetchone()
    if row:
        pid = row["id"]
        conn.execute(
            "UPDATE pages SET title=?, category=?, domain=?, kind=?, content=?, mtime=?, embedding=? WHERE id=?",
            (title, category, domain, kind, content, mtime, emb, pid),
        )
        conn.execute("DELETE FROM pages_fts WHERE rowid = ?", (pid,))
    else:
        cur = conn.execute(
            "INSERT INTO pages (path, title, category, domain, kind, content, mtime, embedding) VALUES (?,?,?,?,?,?,?,?)",
            (path, title, category, domain, kind, content, mtime, emb),
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
