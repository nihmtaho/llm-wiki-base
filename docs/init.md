# Init Guide

Cách dựng 1 wiki mới từ `llm-wiki` (đã cài qua `pip install llm-wiki`).

## 1. Cài global base (1 lần per máy)

```bash
llm-wiki base install
```

Lệnh này:
- Tạo `~/.llm-wiki-base/` (hoặc path override qua env `LLM_WIKI_BASE_DIR`)
- Copy `tools/`, `rag/`, `scripts/` từ package vào base
- Copy `requirements.txt`
- Tạo `.venv/` + pip install

Idempotent — chạy lại để sync code mới nhất.

## 2. Chọn loại wiki

### Personal wiki (in-place)

```bash
mkdir my-wiki && cd my-wiki
llm-wiki init personal
```

Lệnh này tạo data-only trong cwd + cài MCP mặc định:
- `raw/inbox/`, `raw/`, `wiki/.proposals/`, `rag/.rag_index/`
- `wiki/index.md`, `wiki/log.md` (skeleton)
- `_schema.md`, `AGENTS.md`, `CLAUDE.md` (agent configs)
- `.gitignore`, `.env` (point to global base)
- `.llm-wiki.toml` (behavior config) + `eval/golden.toml` (query vàng — thay bằng query thật)
- `.agents/skills/` — 7 skill wiki-scoped + `llm-wiki-research` (personal wiki = 1 folder
  nên 2 scope trùng nhau), kèm symlink cho client không đọc chuẩn Agent Skills
- Đặt `[wiki].profile = personal` (+ `[wiki].lang` nếu truyền `--lang`)
- Đăng ký wiki vào `~/.llm-wiki-base/registry.toml` (có `name` + `id` UUID)
- Cài centralized MCP config (`llm-wiki-base-mcp`) cho client chỉ định (default: claude)

Cờ đáng chú ý: `-c/--client` (claude | opencode | zed | commandcode, lặp lại được),
`--mcp-scope user|project`, `--no-mcp`, `--no-register` (test — không ghi registry thật),
`--skills-target universal|claude|both|skip`, `--no-skills`, `--lang`, `--force`.

### Project wiki (subdir trong project)

```bash
cd my-project
llm-wiki init project --root . --wiki-dir project-wiki -c claude -c commandcode
```

Lệnh này:
- Tạo `<root>/<wiki-dir>/` với data + agent configs + `.llm-wiki.toml`
- Đăng ký wiki vào `~/.llm-wiki-base/registry.toml` (`name` = tên wiki-dir; trùng tên
  với wiki khác path → tự thêm hậu tố `-<uuid8>`)
- Cài **centralized** MCP config (`llm-wiki-base-mcp`) — 1 server entry cho toàn máy,
  server đọc registry để tìm wikis. `--mcp-scope user` (mặc định) ghi vào file config
  cá nhân của client; `--mcp-scope project` ghi `<root>/.mcp.json` (claude/commandcode)
  để cả team dùng qua VCS. Init in ra **đường dẫn + key + scope** vừa ghi.
- Cài skills **2 scope**: 7 skill wiki-scoped vào `<wiki-dir>/.agents/skills/`, còn
  `llm-wiki-research` vào `<root>/.agents/skills/` — nó cần thấy mọi wiki, không chỉ một
- Đặt `[wiki].profile = codebase`

Mỗi wiki mới chỉ cần đăng ký vào registry — MCP config không cần cài lại (idempotent).
Skill đã cài là bản copy → nâng cấp package xong phải chạy lại `init` trên từng wiki
(`init` không ghi đè `.llm-wiki.toml` đã tồn tại, chỉ vá thiếu `[wiki]`).

## 3. (Optional) override env

Edit `.env` đã được init:

```bash
# Đổi embedding model
WIKI_EMBED_MODEL=your-model-name
WIKI_EMBED_DIM=768  # phải khớp model

# Tune retrieval (ưu tiên cao hơn .llm-wiki.toml)
WIKI_FUSION=weighted      # quay lại hành vi cũ (default: rrf)
WIKI_CHUNK_BM25=0         # tắt kênh BM25 chunk-level
WIKI_BM25_WEIGHT=0.4      # chỉ có ý nghĩa khi fusion=weighted
WIKI_VEC_WEIGHT=0.6

# Watch intervals (nếu dùng watch.py)
WATCH_INGEST_SEC=10
```

Hầu hết tuning nên nằm trong **`.llm-wiki.toml`** (`[retrieval]`, `[retrieval.weights]`,
`[eval]`) thay vì env — file đó commit vào wiki repo, `llm-wiki config show` cho thấy
giá trị nào đến từ đâu. Đổi embedding model → phải `llm-wiki reindex --full`.

## 4. Thêm nguồn đầu tiên

3 cách:

```bash
# A. Drop file markdown có sẵn
cp ~/my-article.md raw/inbox/

# B. Extract từ URL
.venv/bin/python scripts/extract_url.py "https://example.com/article" "My Article"

# C. Qua MCP từ AI tool khác
# → gọi wiki_submit(title="...", content="...", source="https://...")
```

## 5. Ingest

**Tự động** (recommended):

```bash
.venv/bin/python tools/watch.py
```

Daemon này poll `raw/inbox/` mỗi `WATCH_INGEST_SEC` (default 15s), ingest file, move sang `raw/`.

**Thủ công**:

```bash
.venv/bin/python tools/ingest.py raw/inbox/my-article.md
```

**Reindex toàn bộ** (DB + RAG):

```bash
.venv/bin/python tools/reindex.py
```

## 6. Connect AI tool (centralized MCP)

Sau `init`, MCP config (`llm-wiki-base-mcp`) đã được cài globally — cài **một lần**
duy nhất trên máy (idempotent). Server đọc `~/.llm-wiki-base/registry.toml` để biết
tất cả wikis.

Reload client (Claude Code / OpenCode / Zed) để pick up server.

**Targeting wiki trong MCP tools:**
- `wiki_search(query)` → cross-wiki search (tất cả wikis, bao gồm cả personal wiki)
- `wiki_search(query, wiki="my-project")` → search trong 1 wiki cụ thể
- `wiki_submit(..., wiki="my-project")` → nạp vào inbox của wiki cụ thích
- `wiki_read(path)` → tự động tìm path trong all wikis; `wiki_read(path, wiki="...")` để chỉ định

**Quản lý registry:**
```bash
llm-wiki wiki list           # list all registered wikis
llm-wiki wiki add <name> <path> --type project  # register wiki đã có sẵn
llm-wiki wiki remove <name>  # xóa khỏi registry (files không bị xóa)
```

## 7. Verify

```bash
# Search test
PYTHONPATH=tools .venv/bin/python -c "
import db,search
from embed import EmbedProvider
print(search.hybrid_search(db.get_conn(),'your first source',provider=EmbedProvider()))
"

# Lint
PYTHONPATH=tools .venv/bin/python -c "
import db,lint
print(lint.lint(db.get_conn()))
"
```

## 8. Obsidian (optional)

Nếu muốn dùng Obsidian để đọc/edit wiki:
- Mở Obsidian → "Open folder as vault" → chọn wiki dir.
- `obsidian-base.base` nằm trong package, copy về root nếu muốn dùng view.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'fastembed'`** — `pip install -r requirements.txt` chưa chạy, hoặc `.venv` chưa active.
- **`sqlite3.OperationalError: no such module: fts5`** — Python build không có FTS5. Cài `python3` từ python.org hoặc dùng `brew install python`.
- **Search trả 0 results** — chưa ingest. Chạy `tools/reindex.py` hoặc `tools/ingest.py <path>`.
- **`wiki_lint` báo `orphans: ['wiki/index.md', 'wiki/log.md']`** — đó là top-level files, không phải page. Bỏ qua.
- **MCP server báo "rag index chưa build"** — chạy `rag/index.py` rồi gọi lại `semantic_search`.
- **`llm-wiki base install` fail** — check Python >= 3.10, `pip install llm-wiki` đã chạy.
