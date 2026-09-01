# llm-wiki

LLM-maintained wiki — compile knowledge 1 lần, maintain mãi. Hybrid BM25+vector search, MCP bridge, multi-base init (personal/project).

**Kiến trúc 2 lớp:**
- **Global runtime** `~/.llm-wiki-base/` — tools, rag, scripts, 1 venv. Share giữa mọi wikis.
- **Per-wiki data** — mỗi wiki là 1 folder chỉ chứa data (raw, wiki, rag_index, .env). Không code, không venv.

**3 đối tượng data:**
- `raw/inbox/` — staging, file mới chờ ingest.
- `raw/` — local cache sau ingest (gitignored, có thể xoá). URL trong `sources:` là primary provenance.
- `wiki/` — knowledge thực sự (curated, cross-linked, persistent). LLM sở hữu.

Local-first. Python + SQLite (FTS5 BM25) + vector (fastembed on-device).

---

## 2 base variant

| | Personal | Project |
|---|---|---|
| **Dùng cho** | Knowledge wiki cá nhân | Wiki cho project codebase |
| **Init location** | In-place (cwd) | `<root>/<wiki-dir>/` subfolder |
| **MCP** | Auto-install (centralized) | Auto-install (centralized) |
| **Skills** | `llm-wiki-{ingest,query,lint,translate}` | `wiki-project-{research,plan,ingest,lint,mcp}` |
| **Skill location** | `<wiki>/.agents/skills/` (per-wiki) | `<wiki>/.agents/skills/` (per-wiki) |

2 base không xung đột — skill prefix khác nhau. MCP là centralized (`llm-wiki-base-mcp`),
1 server entry trên máy, đọc `registry.toml` để biết các wiki.

---

## Cài đặt

```bash
# 1. Clone + install package (Python 3.10+)
git clone <url> llm-wiki-base
cd llm-wiki-base
pip install -e .

# 2. Cài global runtime (1 lần per máy)
llm-wiki base install
# → ~/.llm-wiki-base/{tools/, rag/, scripts/, .venv/}

# 3. Tạo wiki
mkdir my-wiki && cd my-wiki
llm-wiki init personal
# → raw/, wiki/, rag/.rag_index/, .env, .agents/skills/

# 4. Dùng
llm-wiki ingest raw/inbox/my-source.md
```

### Làm lệnh `llm-wiki` khả dụng toàn cục

`pip install -e .` (bước 1) thường chạy trong venv của repo, nên script `llm-wiki` chỉ nằm ở `<repo>/.venv/bin/llm-wiki` (macOS/Linux) hoặc `<repo>/.venv/Scripts/llm-wiki.exe` (Windows) — **không nằm trên PATH**, khiến lệnh `llm-wiki` báo `command not found` ở thư mục khác. Chọn 1 cách:

**macOS / Linux — symlink vào `/usr/local/bin` (khuyên dùng):**
```bash
sudo ln -s "$(pwd)/.venv/bin/llm-wiki" /usr/local/bin/llm-wiki
# Mở terminal mới, xác nhận:
llm-wiki --help
```

**macOS / Linux — thêm `.venv/bin` vào PATH (không cần sudo):**
```bash
echo 'export PATH="'"$(pwd)"'/.venv/bin:$PATH"' >> ~/.zshrc   # hoặc ~/.bashrc
source ~/.zshrc
```

**Windows — symlink (chạy CMD/PowerShell với quyền Admin):**
```powershell
# CMD (Admin)
mklink C:\Windows\llm-wiki.exe "%CD%\.venv\Scripts\llm-wiki.exe"
```
```powershell
# Hoặc PowerShell (Admin)
New-Item -ItemType SymbolicLink -Path "C:\Windows\llm-wiki.exe" -Target "$PWD\.venv\Scripts\llm-wiki.exe"
```

**Windows — thêm `.venv\Scripts` vào PATH (không cần Admin):**
```powershell
[Environment]::SetEnvironmentVariable("Path", "$env:Path;$PWD\.venv\Scripts", "User")
# Mở terminal mới để áp dụng
```

**Dự phòng — chạy trực tiếp qua venv (mọi OS):**
```bash
# macOS/Linux
./.venv/bin/llm-wiki base install
# Windows
.venv\Scripts\llm-wiki.exe base install
```

---

## Cấu trúc

```
~/.llm-wiki-base/                    # Global runtime (1 lần install)
├── tools/                           #   ingest.py, lint.py, watch.py, mcp_base_server.py, db.py, ...
├── rag/                             #   embeddings.py, index.py, search.py
├── scripts/                         #   extract_url.py, extract_pdf.py, extract_youtube.py
├── .venv/                           #   1 Python venv cho mọi wikis
├── registry.toml                    #   centralized MCP: wiki name → path/type
└── requirements.txt

my-wiki/                             # Per-wiki data (1 folder = 1 wiki)
├── .agents/skills/                  #   Skills per-wiki (AI tool load từ đây)
│   ├── llm-wiki-ingest/SKILL.md
│   ├── llm-wiki-query/SKILL.md
│   ├── llm-wiki-lint/SKILL.md
│   └── llm-wiki-translate/SKILL.md
├── raw/                             #   inbox/ + cache (gitignored, có thể xoá)
├── wiki/                            #   markdown + .wiki.db + .proposals/
│   ├── index.md                     #     top-level TOC
│   ├── log.md                       #     append-only reverse-chronological
│   ├── .wiki.db                     #     SQLite + FTS5 search index
│   ├── .proposals/                  #     staging cho human-gated edits
│   └── <domain>/                    #     N domain, mỗi domain có index.md + entity/concept/source/task/
├── rag/.rag_index/                  #   chunk embeddings (binary, per-wiki)
├── .env                             #   LLM_WIKI_BASE_DIR + embedding config
└── .llm-wiki.toml                   #   translation config (optional)
```

---

## CLI

### Global runtime

```bash
llm-wiki base install              # ~/.llm-wiki-base/ (default)
llm-wiki base install --force      # recreate venv + reinstall
llm-wiki base path                 # print current base dir
```

### Init

```bash
# Interactive wizard (chọn personal/project + options)
llm-wiki init                                     # guided flow

# Personal wiki (data + MCP + skills, in-place)
llm-wiki init personal
llm-wiki init personal --name "My Knowledge"
llm-wiki init personal --client claude --client opencode  # MCP clients
llm-wiki init personal --no-mcp                  # skip centralized MCP
llm-wiki init personal --skills-target claude    # .claude/skills/ + symlink
llm-wiki init personal --skills-target both      # copy cả 2
llm-wiki init personal --no-skills               # skip skill install

# Project wiki (data + centralized MCP + registry + skills)
llm-wiki init project --client claude --client opencode
llm-wiki init project --wiki-dir project-wiki    # subfolder name
llm-wiki init project --no-mcp                   # skip centralized MCP
llm-wiki init project --server-name my-wiki-mcp  # custom centralized server name
llm-wiki init project --skills-target universal   # default
```

### Wiki management (centralized MCP registry)

```bash
llm-wiki wiki list                           # list all registered wikis
llm-wiki wiki add my-wiki /path/to/wiki --type personal  # register existing wiki
llm-wiki wiki remove my-wiki                 # unregister (files không bị xóa)
```

Trong centralized MCP, dùng param `wiki=<name>` để target wiki, để trống để cross-wiki search.

### Per-wiki operations (cwd = wiki dir)

```bash
llm-wiki ingest raw/inbox/foo.md   # index 1 source vào search DB
llm-wiki reindex                    # rebuild DB + RAG index
llm-wiki lint                       # health check (orphan, broken link, stale)
llm-wiki watch                      # daemon: scan inbox → ingest → reindex → lint
```

### Translation

```bash
llm-wiki translate enable --lang vi --lang ja   # ghi vào .llm-wiki.toml
llm-wiki translate status                        # xem trạng thái
llm-wiki translate disable                       # disable (giữ langs)
llm-wiki translate check --lang vi               # verify đồng bộ
```

---

## Skills

Skills được copy vào `<wiki>/.agents/skills/` khi init. AI tool load từ đây (không phải từ global base).

| Skill | Base | Vai trò |
|---|---|---|
| `llm-wiki-ingest` | personal | Nạp source mới, auto-detect domain, cross-link, update index/log |
| `llm-wiki-query` | personal | Search wiki, tổng hợp trả lời có cite |
| `llm-wiki-lint` | personal | Health-check: orphan, broken link, stale, missing index |
| `llm-wiki-translate` | personal | Dịch page sang target lang (dùng LLM của AI tool) |
| `wiki-project-research` | project | Research codebase bằng wiki (ưu tiên) + codegraph (fallback) |
| `wiki-project-plan` | project | Plan mode workflow cho task lớn |
| `wiki-project-ingest` | project | Nạp source vào project-wiki (tech doc, PR, architecture note) |
| `wiki-project-lint` | project | Health-check + stale code reference detection |

**`--skills-target`:**
- `universal` (default): `<wiki>/.agents/skills/` — AI tool universal scan.
- `claude`: `<wiki>/.claude/skills/` + symlink `.agents/skills/` → `.claude/skills/`.
- `both`: copy cả 2 (duplicate, nhưng explicit).

---

## Translation

Wiki song ngữ: EN gốc + 1+ bản dịch `<slug>.<lang>.md`. Bản dịch **KHÔNG vào DB/RAG** (skip rule `*.lang.md`).

```toml
# .llm-wiki.toml
[translate]
enabled = true
langs = ["vi", "ja"]
```

Khi enabled, ingest skill tự gọi `llm-wiki-translate` skill cho mỗi page mới. Bản dịch dùng **LLM của AI tool đang chạy** (Claude Code → Claude, OpenCode → provider). Không cần API key riêng.

```bash
llm-wiki translate enable --lang vi --lang ja
llm-wiki translate check --lang vi   # verify đồng bộ (frontmatter keys + heading structure)
```

---

## MCP bridge

MCP = cầu nối cho AI tool, **KHÔNG** viết thẳng wiki:

| Tool | Vai trò |
|---|---|
| `wiki_search(query, top_k)` | Hybrid BM25 + vector search |
| `semantic_search(query, top_k)` | Chunk-level vector search |
| `wiki_read(path)` | Đọc 1 file |
| `wiki_list(domain, kind)` | Liệt kê pages, filter |
| `list_raw_source(subdir)` | Liệt kê files trong raw/ |
| `read_raw_source(name, subdir)` | Đọc raw source |
| `wiki_submit(title, content, domain, source)` | **Ghi vào `raw/inbox/`** (KHÔNG wiki) |
| `wiki_propose_edit(path, content)` | Staging vào `wiki/.proposals/` |
| `wiki_lint()` | Health-check |

---

## Nguyên tắc an toàn

- **Raw local cache (gitignored)** — user có thể xoá tùy ý. URL trong `sources:` là primary provenance (host bên thứ 3, không bị user xoá). Wiki page đã curated là knowledge "lâu dài" hơn raw.
- **AI proposes, human decides.** Re-derivable writes (index, log) → tự làm. Asserting fact → `wiki_propose_edit` staging.
- **Contradiction** = report cho người, không materialize thành edge.
- **Provenance bắt buộc.** Mọi claim có `[[wiki page]]` trong body hoặc URL trong `sources:`.
- **Copied state drift.** Wiki page KHÔNG chứa value move-able (SHA, mtime, count tuyệt đối). Values nằm trong frontmatter hoặc đọc live từ tooling.

---

## Cross-platform

- macOS, Linux, Windows: full support.
- MCP config: macOS `~/Library/Application Support/`, Linux `$XDG_CONFIG_HOME` (default `~/.config/`), Windows `%APPDATA%`.
- Skills: copy (không symlink) — hoạt động trên mọi OS không cần Developer Mode.

---

## Migrate từ layout cũ

Nếu wiki cũ có `tools/`, `rag/`, `scripts/`, `.venv/` ở local:

```bash
llm-wiki base install
cd /path/to/old-wiki
rm -rf tools/ rag/ scripts/ .venv/
llm-wiki ingest raw/inbox/foo.md   # wrapper dùng global base
```

---

Chi tiết schema: [_schema.md](_schema.md) · Runbook agent: [CLAUDE.md](CLAUDE.md) · Init guide: [docs/init.md](docs/init.md)
