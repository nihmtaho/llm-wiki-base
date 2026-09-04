# llm-wiki

Wiki do LLM bảo trì — compile kiến thức **một lần**, maintain **mãi**. Union retrieval
(BM25 page + BM25 chunk + vector, RRF fusion) có eval harness đo được, MCP bridge cho AI
tool, init được cả wiki cá nhân lẫn wiki của repo code.

Local-first. Python + SQLite (FTS5 BM25) + vector on-device (fastembed). Không dịch vụ
ngoài, không khoá dữ liệu.

> **Xem cách nó chạy:** [`docs/wiki-flow.html`](docs/wiki-flow.html) — sơ đồ canvas động,
> đổi được personal ↔ project, chỉ ra đúng chỗ nào là máy tất định, chỗ nào cần LLM, và
> chỗ nào quyền quyết định nằm ở người.

**Kiến trúc 2 lớp**

- **Global runtime** `~/.llm-wiki-base/` — tools, rag, scripts, 1 venv. Dùng chung cho mọi wiki.
- **Per-wiki data** — mỗi wiki là một folder chỉ chứa data (`raw/`, `wiki/`, `rag/.rag_index/`,
  `.env`, `.llm-wiki.toml`). Không code, không venv.

**Ba tầng quyền hạn** (cái này giải thích phần còn lại của thiết kế)

| tầng | là gì | ai viết | chết được không |
|---|---|---|---|
| `wiki/*.md` | nguồn sự thật, có provenance | skill + LLM, người duyệt | không |
| `raw/` | cache của nguồn gốc (URL mới là provenance chính) | người thả / `wiki_submit` | **có**, xoá tuỳ ý |
| `.wiki.db`, `rag/.rag_index/` | chỉ mục derived | `llm-wiki reindex` | **có**, rebuild được |

---

## Mục lục

- [Cài đặt](#cài-đặt) · [60 giây đầu tiên](#60-giây-đầu-tiên)
- [Cách hoạt động](#cách-hoạt-động)
- [Hai biến thể wiki](#hai-biến-thể-wiki)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [CLI](#cli) · [Skills](#skills) · [Config](#config-llm-wikitoml)
- [Retrieval & eval](#retrieval--eval)
- [Quyền của người: verify · proposals · pins](#quyền-của-người-verify--proposals--pins)
- [MCP bridge](#mcp-bridge)
- [Translation](#translation)
- [Nâng cấp từ bản trước](#nâng-cấp-từ-bản-trước)
- [Nguyên tắc an toàn](#nguyên-tắc-an-toàn) · [Giới hạn đã biết](#giới-hạn-đã-biết)
- [Cross-platform](#cross-platform) · [Phát triển](#phát-triển)

---

## Cài đặt

Yêu cầu: **Python 3.10+** (3.11 trở lên không cần backport `tomli`).

```bash
# 1. Cài package
git clone <url> llm-wiki-base && cd llm-wiki-base
pip install -e .

# 2. Cài global runtime (1 lần / máy)
llm-wiki base install
# → ~/.llm-wiki-base/{tools/,rag/,scripts/,.venv/,registry.toml}

# 3. Tạo wiki
mkdir my-wiki && cd my-wiki && llm-wiki init      # wizard dẫn từng bước
```

### Làm lệnh `llm-wiki` khả dụng toàn cục

`pip install -e .` thường chạy trong venv của repo → script chỉ nằm ở
`<repo>/.venv/bin/llm-wiki` (macOS/Linux) hoặc `<repo>/.venv/Scripts/llm-wiki.exe`
(Windows), **không trên PATH**, nên mở folder khác sẽ báo `command not found`.

**macOS / Linux — symlink (khuyên dùng):**
```bash
sudo ln -s "$(pwd)/.venv/bin/llm-wiki" /usr/local/bin/llm-wiki
```

**macOS / Linux — thêm vào PATH (không cần sudo):**
```bash
echo 'export PATH="'"$(pwd)"'/.venv/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

**Windows — symlink (CMD/PowerShell với quyền Admin):**
```powershell
mklink C:\Windows\llm-wiki.exe "%CD%\.venv\Scripts\llm-wiki.exe"
# hoặc PowerShell: New-Item -ItemType SymbolicLink -Path "C:\Windows\llm-wiki.exe" -Target "$PWD\.venv\Scripts\llm-wiki.exe"
```

**Windows — thêm vào PATH (không cần Admin):**
```powershell
[Environment]::SetEnvironmentVariable("Path", "$env:Path;$PWD\.venv\Scripts", "User")
```

**Dự phòng mọi OS — gọi thẳng qua venv:** `./.venv/bin/llm-wiki base install`
(Windows: `.venv\Scripts\llm-wiki.exe`).

### 60 giây đầu tiên

```bash
mkdir demo && cd demo
llm-wiki init personal -c commandcode --lang vi   # hoặc -c claude / opencode / zed
echo "# Notes\n\nExpo Router SplitView dùng `unstable_splitView`." > raw/inbox/note.md

# Từ đây có 2 việc KHÁC NHAU, đừng nhầm:
llm-wiki ingest raw/inbox/note.md      # (A) tất định: đưa file VÀO SEARCH DB
# (B) viết page wiki = VIỆC CỦA SKILL: mở AI tool, chạy skill `llm-wiki-ingest`

llm-wiki reindex && llm-wiki lint && llm-wiki doctor
```

`llm-wiki doctor` sẽ nói rõ lệnh nào CLI tự làm được, lệnh nào bắt buộc có AI tool.

---

## Cách hoạt động

Đường đi của một tài liệu — 9 bước, và 3 lần đổi "ai đang làm":

1. **Nguồn vào staging.** Người thả file, `scripts/extract_{url,pdf,youtube}.py` tạo ra,
   hoặc AI khác gọi MCP `wiki_submit` → luôn luôn vào `raw/inbox/`. Không có đường tắt
   nào ghi thẳng vào `wiki/`.
2. **Ingest = skill + LLM.** Đọc trọn nguồn, tóm tắt 3–5 takeaway, bàn với người, chọn
   domain, rồi viết `wiki/<domain>/{source,entity,concept}/*.md` kèm provenance.
   CLI `llm-wiki ingest` **không** làm việc này — nó chỉ index.
3. **Ghi catalog.** `index.md` + `log.md` là re-derivable nên agent tự ghi; mọi assertion
   khác thì không. `verified` để trống.
4. **Dựng chỉ mục derived.** `llm-wiki reindex` theo content-hash → `pages_fts`,
   `chunks_fts`, và vector chunk (khi `vector = true`).
5. **Câu hỏi → pool ứng viên.** Skill gọi MCP `wiki_search` với `top_k = 2 × top_n_final`.
6. **RRF.** Ba kênh xếp hạng độc lập → gộp bằng hạng, không cộng thẳng score.
7. **Rerank bằng LLM** (skill, không phải model trong code) → cắt xuống `top_n_final`.
8. **Trả lời có cite** + gắn cờ page unverified/stale. Synthesis hay → file ngược thành
   page mới để wiki compounding.
9. **Cổng người.** Muốn sửa/claim: `wiki_propose_edit` → `.proposals/` →
   `llm-wiki proposals apply --by <bạn>` → `verify`.

Hai chiều đi ngược (đảm bảo wiki không mục rữa): `llm-wiki watch` chạy vòng 1→4 khi có file
mới; `llm-wiki lint` (tất định) rồi skill `llm-wiki-review` (ngữ nghĩa) đổ gap vào
`wiki/alerts/`.

Bản chữ + sơ đồ động: [`docs/wiki-flow.html`](docs/wiki-flow.html).

---

## Hai biến thể wiki

| | Personal | Project (codebase) |
|---|---|---|
| **Dùng cho** | Knowledge wiki cá nhân | Wiki của một repo code |
| **Vị trí** | In-place (cwd) | `<root>/<wiki-dir>/` subfolder |
| **`[wiki].profile`** | `personal` | `codebase` |
| **Domain** | tự do theo chủ đề | `tech-stack`, `architecture`, `conventions`, `dependencies`, `deployment`, `testing`, `security`, `api`, `data-model` |
| **1 source chạm** | 10–15 page | 5–10 page (focused hơn) |
| **Đặc thù** | từ vựng/ngữ pháp phải vào wiki | **mọi code path phải verify** trước khi ghi; tách intent ↔ observation |
| **Skills** | `llm-wiki-{ingest,query,lint,reindex,review,consolidate,translate}` | cùng bộ **+ `llm-wiki-research` ở root repo** |
| **MCP** | ghi vào chính wiki (`.mcp.json` / `opencode.jsonc`, commit được) | ghi vào root repo (`.mcp.json` / `opencode.jsonc`, commit được) |
| **Code navigation** | — | khuyến nghị user tự cài plugin codegraph ở root repo (agent tự dùng khi thấy) |

Hai biến thể **dùng chung tên skill** — khác nhau ở `[wiki].profile`, không ở bộ skill.
MCP là centralized (`llm-wiki-base-mcp`): một server entry trên máy, đọc `registry.toml`
để biết có wiki nào.

---

## Cấu trúc thư mục

```
~/.llm-wiki-base/                    # Global runtime (install 1 lần)
├── tools/                           #   search.py, reindex.py, ingest.py, lint.py, eval.py,
│                                    #   chunking.py, db.py, proposals.py, watch.py,
│                                    #   clean_sources.py, embed.py, paths.py, config_file.py,
│                                    #   mcp_base_server.py (centralized) + mcp_server.py (legacy per-wiki)
├── rag/                             #   index.py, search.py, embeddings.py
├── scripts/                         #   extract_url.py, extract_pdf.py, extract_youtube.py
├── templates/                       #   eval-golden.toml (cho `eval --init`)
├── .venv/                           #   1 Python venv cho mọi wiki
├── registry.toml                    #   name + id + path + type của từng wiki
└── requirements.txt

my-wiki/                             # Per-wiki data (1 folder = 1 wiki)
├── .agents/skills/                  #   7 skill wiki-scoped + manifest .llm-wiki-skills.json
│   ├── llm-wiki-ingest/SKILL.md     #   (+ llm-wiki-research: wiki cá nhân cũng có;
│   ├── …                            #    project wiki đặt nó ở ROOT repo)
├── raw/                             #   inbox/ (staging) + cache (gitignored, xoá được)
├── wiki/                            #   markdown + DB + staging
│   ├── index.md                     #     TOC top-level (reserved — không chunk)
│   ├── log.md                       #     append-only reverse-chronological (reserved)
│   ├── .wiki.db                     #     SQLite: pages + pages_fts + chunks_fts
│   ├── .proposals/                  #     staging edit của AI, có metadata target
│   ├── pins.yml                     #     sửa tay của human, sống qua regenerate
│   ├── alerts/                      #     hàng đợi gap từ review skill
│   └── <domain>/                    #     index.md + entity/concept/source/task/
├── eval/
│   ├── golden.toml                  #     query vàng (dữ liệu — COMMIT)
│   └── results.json                 #     lịch sử đo (gitignored)
├── rag/.rag_index/                  #     chunk embeddings (binary, per-wiki)
├── .env                             #     đường dẫn runtime (gitignored)
└── .llm-wiki.toml                   #     behavior config (COMMIT)

<repo>/                              # chỉ với project wiki
└── .agents/skills/llm-wiki-research #     skill xuyên wiki, cần thấy MỌI wiki
```

---

## CLI

### Global runtime

```bash
llm-wiki base install              # → ~/.llm-wiki-base/ (default)
llm-wiki base install --force      # tạo lại venv + cài lại requirements
llm-wiki base path                 # in base dir hiện tại
```

### Init

```bash
llm-wiki init                                     # wizard tương tác

# Personal
llm-wiki init personal --name "My Knowledge" --lang vi
llm-wiki init personal -c claude -c commandcode   # client MCP (lặp lại được)
llm-wiki init personal --no-mcp                   # bỏ qua MCP
llm-wiki init personal --no-register              # không ghi registry.toml (test/script)
llm-wiki init personal --skills-target claude     # + symlink .claude/skills/
llm-wiki init personal --no-skills                # bỏ cài skill

# Project
llm-wiki init project -c claude -c opencode
llm-wiki init project --wiki-dir project-wiki     # tên subfolder chứa wiki
llm-wiki init project --lang vi
llm-wiki init project --server-name my-wiki-mcp   # đổi tên centralized server
llm-wiki init project --no-register               # tránh làm bẩn registry khi test
```

Client chấp nhận: `claude`, `opencode`, `zed`, `commandcode`. Init ghi MCP entry
(`llm-wiki-base-mcp`) vào **file MCP per-project/personal wiki** (`.mcp.json` cho
claude/commandcode, `opencode.jsonc` cho opencode — nằm trong chính wiki/repo, commit
vào VCS được). Client chưa có file project-scope (vd `zed`) thì init báo bỏ qua.
Init **in ra đường dẫn file vừa ghi + key** để bạn biết chính xác nó sửa gì.

### Wiki management (registry)

```bash
llm-wiki wiki list
llm-wiki wiki add my-wiki /path/to/wiki --type personal
llm-wiki wiki remove my-wiki            # accept name hoặc id; không xoá file
```

Mỗi wiki có `name` (key tra cứu dễ đọc — dùng làm tham số `wiki=`) và `id` (UUID máy sinh,
ổn định). Trùng `name` mà khác path → init **tự thêm hậu tố `-<uuid8>`** thay vì đá wiki
cũ khỏi registry trong im lặng. `wiki=` của MCP accept cả hai.

### Thao tác per-wiki (cwd = wiki dir)

```bash
llm-wiki ingest raw/inbox/foo.md    # index 1 source vào search DB (không viết page)
llm-wiki reindex                    # tăng dần theo content-hash (+ chunks_fts)
llm-wiki reindex --check            # dry-run: sẽ index/xoá gì + config drift + trạng thái chunk index
llm-wiki reindex --full             # rebuild toàn bộ (sau khi đổi embed_model/chunk_tokens/vector/fusion)
llm-wiki lint                       # health-check tất định (orphan, broken link, frontmatter, …)
llm-wiki lint --fix                 # xoá dangling rows + thêm index entry còn thiếu (additive)
llm-wiki eval                       # P@k / R@k / MRR trên query vàng (read-only)
llm-wiki eval --compare             # tier1-weighted / rrf-text / rrf+vector + verdict bật vector
llm-wiki eval --init                # tạo eval/golden.toml từ template
llm-wiki proposals list             # đề xuất đang chờ duyệt + độ lớn diff
llm-wiki proposals show <name>      # metadata + unified diff so với page hiện tại
llm-wiki proposals apply <name> [--by <human-id>]   # ghi page + log + reindex + xoá proposal
llm-wiki proposals discard <name> --force
llm-wiki proposals new -t wiki/x/y.md -f body.md    # tạo proposal từ CLI
llm-wiki config show                # effective config, mỗi key ghi rõ [default]/[toml]/[env …]
llm-wiki verify wiki/<d>/concept/x.md --by <human-id>
llm-wiki verify <path> --unverify
llm-wiki watch                      # daemon: inbox → ingest → reindex → lint (+ nhắc review due)
llm-wiki doctor                     # kiểm môi trường + ranh giới CLI ↔ AI tool
```

**`llm-wiki doctor`** kiểm: base runtime có tồn tại không; `tools/` trong base có **lệch**
với package không (so từng file, nhắc `llm-wiki base install`); deps trong base venv
(`mcp`, `fastembed`, và `tomli` chỉ khi venv < 3.11); registry (path ma → FAIL, wiki thiếu
`id` → WARN); wiki hiện tại (có `.llm-wiki.toml`, có `[wiki].profile`, đã đăng ký chưa,
còn proposal tồn đọng không); cuối cùng là bảng **6 việc bắt buộc có AI tool**.
FAIL → exit 1, WARN → vẫn 0.

### Translation

```bash
llm-wiki translate enable --lang vi --lang ja   # ghi vào .llm-wiki.toml (giữ comment)
llm-wiki translate status                       # xem trạng thái
llm-wiki translate disable                      # tắt, giữ langs
llm-wiki translate check --lang vi              # verify đồng bộ frontmatter + heading
```

---

## Skills

8 skill, **không chia tên personal/project** — chế độ đọc từ `[wiki].profile`. Cài lúc
`llm-wiki init`, chia 2 scope:

| Skill | Scope | Vai trò |
|---|---|---|
| `llm-wiki-ingest` | wiki | raw → source/entity/concept page + cross-link + index/log + reindex |
| `llm-wiki-query` | wiki | trả lời từ **wiki đang đứng**: retrieval → rerank → cite → file synthesis |
| `llm-wiki-lint` | wiki | health-check **tất định**: orphan, broken link, frontmatter, index sync |
| `llm-wiki-reindex` | wiki | dựng/chẩn đoán chỉ mục derived: `--check`, `--full`, kênh nào chết |
| `llm-wiki-review` | wiki | health-check **sinh sinh**: mâu thuẫn, stale, trust gap → `wiki/alerts/` |
| `llm-wiki-consolidate` | wiki | gộp log/mẩu rải rác → concept canonical (additive, distill-verify) |
| `llm-wiki-translate` | wiki | dịch page sang `[translate].langs` (dùng LLM của AI tool) |
| `llm-wiki-research` | **codebase root** | research **xuyên nhiều wiki** qua centralized MCP |

`llm-wiki-research` cài ở `<root_repo>/.agents/skills/` chứ không nằm trong wiki: nó cần
thấy mọi wiki, còn skill wiki-scoped chỉ lo một wiki. Ranh giới với `query`: *query* = một
wiki bạn đang đứng (được phép ghi synthesis), *research* = nhiều wiki (chỉ được staging).

**Phân phối — `.agents/skills/` là bản canonical duy nhất:**

| `--skills-target` | kết quả |
|---|---|
| `universal` (default) | copy vào `.agents/skills/` + symlink cho client truyền qua `-c` |
| `claude` | như trên + chắc chắn link `.claude/skills/` |
| `both` | link cả `.claude/skills/` và `.opencode/commands/` |
| `skip` | không cài (`--no-skills`) |

- **Command Code** đọc `.agents/skills/` (project) và `~/.agents/skills/` (user) trực tiếp
  → không cần link. Tạo `.commandcode/skills/` sẽ bị ưu tiên cao hơn `.agents/` và sinh
  cảnh báo trùng tên khi hai bản lệch nhau.
- **Claude Code**: dir symlink `.claude/skills/<name>` → `.agents/skills/<name>`.
- **OpenCode**: file symlink `.opencode/commands/<name>.md` → `.agents/skills/<name>/SKILL.md`.
- **Zed**: không có skill system (chỉ nhận MCP).
- Windows không có quyền symlink → tự fallback sang copy.

Skill đã cài là **bản copy** → nâng cấp package xong phải chạy lại `llm-wiki init …` trên
từng wiki. Re-init **tự prune** skill do llm-wiki cài mà bản mới không còn ship (theo
manifest `.agents/skills/.llm-wiki-skills.json`); skill bạn tự viết cùng folder được giữ.

---

## Config (`.llm-wiki.toml`)

Behavior config per-wiki, **commit** vào wiki repo. Precedence: **env > TOML > default**.

```toml
[wiki]
profile = "personal"      # personal | codebase — init set đúng loại; skill đọc để chọn chế độ
lang = "en"               # ngôn ngữ agent VIẾT page (không phải đích dịch)

[retrieval]
fusion = "rrf"            # "weighted" = hành vi cũ: rollback 1 dòng, cũng là baseline A-B
chunk_bm25 = true         # kênh BM25 trên semantic chunks
vector = true             # bật mặc định (đo được); tắt nếu eval của chính wiki không cho Δ>0
rerank = "llm"            # skill layer rerank — Python không đọc key này
chunk_tokens = 512        # chỉ tác dụng khi một section dài hơn mức đó (đo: wiki ngắn thì không đổi gì)
top_k_bm25 = 20           # ứng viên mỗi kênh text
top_k_vector = 20         # ứng viên kênh vector
top_n_final = 8           # kết quả cuối + budget đọc của skill
relax_recall = true       # giữ nguyên → AND sanitize → OR một lần (CJK-safe)

[retrieval.weights]       # RRF chỉ nhạy TỈ số
bm25_page = 1.0
bm25_chunk = 1.0
vector = 1.0

[retrieval.index]
embed_model = ""          # rỗng = builtin

[models]                  # HỢP ĐỒNG SKILL LAYER — Python không gọi LLM, không đọc key này
light = ""                # model để WRITE (sinh concept)
heavy = ""                # model để VERIFY/review
provider = ""             # openai-compatible | anthropic | ollama; rỗng = dùng LLM của AI tool
api_key_env = ""          # TÊN biến env chứa key — không bao giờ ghi key thẳng vào file

[eval]
k = 8                     # cutoff của `llm-wiki eval`

[review]
interval_days = 7         # review skill chỉ chạy full khi quá mốc
max_pages = 80

[lifecycle]
default_stale_after_days = 180

[lint]
banned_terms = []
```

Đổi `embed_model` / `chunk_tokens` / `vector` / `fusion` → chạy `llm-wiki reindex --full`.
Runtime plumbing (đường dẫn) vẫn qua `.env` + env vars.

Hai key `chunk_tokens` và `rrf_k` **đã đo là không có tác dụng** trên wiki nhỏ: 256/512/1024
cho cùng số chunk khi mọi section đều ngắn, và sweep `rrf_k` 20→250 cho số liệu giống hệt.
Đừng đổi chúng cho tới khi eval của chính wiki bạn chỉ ra khác biệt.

`llm-wiki init` không ghi đè `.llm-wiki.toml` đã tồn tại (chỉ vá thiếu `[wiki]`), và mọi
lệnh ghi vào file này (`translate enable`, `init` set profile) **giữ nguyên comment** —
comment ở đây là tài liệu, không phải trang trí.

Env override: `WIKI_EMBED_MODEL`, `WIKI_FUSION`, `WIKI_CHUNK_BM25`, `WIKI_BM25_WEIGHT`,
`WIKI_VEC_WEIGHT` (2 cái cuối chỉ chi phối khi `fusion = "weighted"`). Installer **không**
pin env retrieval vào MCP entry — pin ở đó làm `.llm-wiki.toml` bị vô hiệu riêng trong MCP
(env > TOML) trong khi CLI vẫn đọc, tức cùng một wiki ra hai kết quả khác nhau.

---

## Retrieval & eval

**Union retrieval + RRF** (`wiki_search` / `tools/search.py`): ba kênh xếp hạng độc lập rồi
gộp bằng **reciprocal rank fusion trên hạng** — không cộng thẳng score vì `bm25()` và cosine
khác thang hoàn toàn.

| kênh | hạ tầng | ghi chú |
|---|---|---|
| `bm25_page` | FTS5 `pages_fts` (wiki + raw) | luôn chạy |
| `bm25_chunk` | FTS5 `chunks_fts` trong `.wiki.db` | bắt term hiếm nằm sâu trong page dài |
| `vector_chunk` | `rag/.rag_index/{chunks.json,vectors.npy}` | chỉ khi `vector = true` |

Hai kênh chunk **dùng chung** `tools/chunking.py` nên cùng ranh giới — nếu khác nhau thì
RRF giữa chúng vô nghĩa. Mỗi kết quả có `matched_by` + `rank` + `snippet` (có thể là text
của một chunk: đủ để **chọn** page, không đủ để **trả lời**). **Không chunk:**
`index.md`/`log.md` (reserved), bản dịch `*.lang.md`, frontmatter, footnote trích nguyên văn.

**Rerank ở skill layer** (`[retrieval].rerank = "llm"`): skill xin pool rộng
(`2 × top_n_final`), chấm ứng viên bằng title/snippet/`matched_by` mà chưa mở file, rồi mới
mở `top_n_final` page. Không thêm reranker model vào code.

**Fallback tất định, nhưng không im lặng:** thiếu model / chưa build chunk → từng kênh tự
tắt và **được báo** (`reindex --check` nói "chưa build", `eval` in `[ERROR] kênh bị tắt vì
lỗi`). Số liệu trông hợp lệ trong khi một phần đang chết là bug, không phải kết quả.

```bash
llm-wiki eval --init          # tạo eval/golden.toml (đó là dữ liệu — COMMIT)
llm-wiki eval                 # P@k / R@k / MRR theo config hiện tại
llm-wiki eval --compare       # tier1-weighted / rrf-text / rrf+vector + verdict
llm-wiki eval --compare -v    # thêm số liệu từng query
```

`eval/golden.toml` chứa query **thật** + danh sách concept chấp nhận được; eval cảnh báo khi
`relevant path` không khớp page nào trong DB thay vì âm lặng tính điểm sai. Kết quả append
`eval/results.json` (gitignored) kèm fingerprint config → so sánh được theo thời gian.
`zero_recall_queries` = wiki thiếu tài liệu (việc của ingest), không phải retriever dở.

**Điều kiện bật vector:** ΔR@k của profile `+vector` dương rõ rệt trên bộ query vàng của
*chính wiki đó*. Template mới bật sẵn `vector = true` vì có bằng chứng đo; wiki cũ nâng cấp
vẫn `false` cho tới khi bạn tự `eval --compare`. Ở scale rất nhỏ (< ~50k token) BM25
thường đã đủ.

**Cái bẫy đã đo được của RRF** (một wiki thật, 18 query / 21 page): với weight bằng nhau,
page đứng hạng *giữa ở cả hai* kênh (đồng thuận) có thể bị page hạng 1 ở một kênh + hạng 11
ở kênh kia chèn mất ngay sát cutoff — text-only RRF **mất** một query mà weighted-sum cũ tìm
ra. Ba đòn bẩy đã đo:

- `rrf_k` **không phải** đòn bẩy: sweep 20 → 250 cho số liệu giống hệt.
- `weights.bm25_page = 2.0` cứu lại query đó (R@8 ngang vector) nhưng **MRR tụt** dưới cả
  rrf-text → chỉ dùng khi không muốn bật vector.
- `vector = true` cho cả recall tốt nhất lẫn first-hit tốt nhất (kênh vector bắt paraphrase
  không trùng từ — đúng case mà text fail): R@8 0.9167 → **0.9722**, MRR 0.8518 → **0.8981**.

Tóm lại: RRF tốt hơn weighted-sum về *độ phủ*, không tự động tốt hơn về *first hit*. Đó là
lý do có eval harness thay vì tin lý thuyết rank-fusion.

---

## Quyền của người: verify · proposals · pins

**Trust tier.** Mỗi page có `generated: {by, at}` (ai sinh). Tuỳ chọn `verified: {by, at}`:

- **unverified** — không có `verified` (mặc định khi AI viết).
- **human-reviewed** — `verified.by = "human:<id>"`.

```bash
llm-wiki verify wiki/<domain>/concept/x.md --by <human-id>
llm-wiki verify <path> --unverify            # hạ về unverified
```

AI **không** tự set `verified`. Retrieval vẫn trả page unverified, nhưng skill phải gắn cờ.

**Proposals = cổng ghi.** AI đọc wiki thì tự do, khẳng định sự thật thì phải có người ký:

```bash
llm-wiki proposals list                 # proposal nào, nhắm page nào, diff bao nhiêu
llm-wiki proposals show <name>          # unified diff so với page hiện tại
llm-wiki proposals apply <name>         # ghi page + log + reindex + xoá proposal
llm-wiki proposals apply <name> --by you   # …và set verified = human:you
llm-wiki proposals discard <name> --force
```

MCP `wiki_propose_edit(path, content, wiki)` ghi cùng format: file mang header metadata
(`target`, `wiki`, `created`, `by`, `note`) bên trong HTML comment, phần còn lại là nội dung
nguyên văn sẽ ghi vào page. Proposal cũ không metadata vẫn đọc được — `list`/`show` đoán
target từ tên file, nhưng `apply` **từ chối** ghi khi chưa có `--target` tường minh (đoán
sai là đè lên page thật).

**Pins.** Sửa tay quan trọng → ghi vào `wiki/pins.yml` (claim + anchor heading).
Ingest/consolidate không được ghi đè section mà pin bám vào; nguồn mới phủ định pin →
đẩy vào `wiki/alerts/`, không revert âm thầm.

---

## MCP bridge

MCP là **cầu nối** cho AI tool — không phải kênh để ghi thẳng wiki.

| Tool | Vai trò |
|---|---|
| `wiki_search(query, top_k, wiki)` | Union retrieval + RRF: `bm25_page` ∪ `bm25_chunk` ∪ `vector_chunk`; mỗi kết quả có `matched_by` + `rank` + `snippet`. `top_k = 0` → theo `top_n_final` |
| `semantic_search(query, top_k, wiki)` | Vector search thô cấp chunk (chỉ để tìm concept, không phải nguồn trả lời) |
| `wiki_read(path, wiki)` | Đọc 1 file |
| `wiki_list(domain, kind, wiki)` | Liệt kê pages, filter |
| `list_raw_source(subdir, wiki)` | Liệt kê file trong `raw/` |
| `read_raw_source(name, subdir, wiki)` | Đọc raw source |
| `wiki_submit(title, content, wiki, …)` | **Ghi vào `raw/inbox/`** — cổng nạp duy nhất, `wiki` bắt buộc |
| `wiki_propose_edit(path, content, wiki)` | Staging vào `wiki/.proposals/` (kèm metadata target) |
| `wiki_lint(wiki)` | Health-check tất định |

Resources: `registry://wikis`, `wiki://<name>/index`, `wiki://<name>/log`.
Rerank **không phải MCP tool** — đó là bước LLM trong skill `llm-wiki-query` /
`llm-wiki-research`.

**Cài MCP cho client** (`llm-wiki init -c …`) — luôn ghi vào file MCP
per-project/personal wiki (commit vào VCS được, cả team dùng chung):

| client | file (trong wiki/repo) | key |
|---|---|---|
| `claude` | `<root>/.mcp.json` | `mcpServers` |
| `commandcode` | `<root>/.mcp.json` | `mcpServers` |
| `opencode` | `<root>/opencode.jsonc` | `mcp` |
| `zed` | chưa có file project-scope → init báo bỏ qua | `context_servers` |

Entry trỏ vào `["llm-wiki", "serve", "--mcp"]` (như `codegraph serve --mcp`) —
`llm-wiki` phải có trên PATH để agent launch được server
(`sudo ln -s "$(pwd)/.venv/bin/llm-wiki" /usr/local/bin/llm-wiki`).

Khởi động lại AI tool sau khi init — process MCP cũ giữ `registry.toml` trong memory.

---

## Translation

Wiki song ngữ: bản gốc + 1+ bản dịch `<slug>.<lang>.md`. Bản dịch **không vào DB/RAG**
(skip rule `*.lang.md`), nên không bao giờ cạnh tranh với bản gốc khi tìm.

```toml
# .llm-wiki.toml
[translate]
enabled = true
langs = ["vi", "ja"]
```

Khi enabled, skill ingest gọi skill `llm-wiki-translate` cho mỗi page mới. Bản dịch dùng
**LLM của AI tool đang chạy** — không cần API key riêng, không thêm dependency vào
pipeline Python.

---

## Nâng cấp từ bản trước

```bash
pip install -e . && llm-wiki base install           # 1. sync code → ~/.llm-wiki-base/
cd <wiki-cũ> && llm-wiki reindex --full             # 2. build chunks_fts + sửa FTS duplicate rows
cd <wiki-cũ> && llm-wiki init personal -c claude    # 3. refresh skills + MCP (trả lời yes)
llm-wiki doctor                                     # 4. xem còn thiếu gì
```

- Bước 2 bắt buộc một lần: incremental bỏ qua page không đổi content-hash, nên wiki cũ
  không bao giờ có chunk nếu không `--full`.
- **Skills gộp + đổi tên**: 13 skill personal/project → 8 skill `llm-wiki-*` profile-aware.
  Re-init **tự xoá** `wiki-project-*` cũ và giữ skill bạn tự viết. Project wiki nhận thêm
  `llm-wiki-research` ở **root repo**.
- **`vector = true` thành mặc định** của template mới. Wiki cũ giữ `false` cho tới khi bạn
  `eval --compare`; bật lên thì `reindex --full` để dựng `rag/.rag_index`.
- Registry có **`id` (UUID)**; `init`/`wiki add` gán tự động. Trùng tên khác path không còn
  đá nhau im lặng.
- `--no-register` (và env `LLM_WIKI_REGISTRY`) để test không ghi registry thật.
- Thứ tự rank của `wiki_search` **đổi** (RRF thay weighted sum). Muốn hành vi cũ:
  `fusion = "weighted"` — một dòng, và cũng là baseline để A-B.
- `semantic_search` không trả chunk của `index.md`/`log.md` nữa (chủ đích).
- Code cũ vẫn mở DB mới bình thường (`chunks_fts` chỉ được code mới đọc).
- `llm-wiki proposals …` là lệnh mới để duyệt `.proposals/`; proposal cũ cần
  `apply --target <path>` tường minh.

**Wiki layout cũ** (có `tools/`, `rag/`, `scripts/`, `.venv/` nằm trong wiki):

```bash
llm-wiki base install
cd /path/to/old-wiki && rm -rf tools/ rag/ scripts/ .venv/
llm-wiki reindex          # wrapper dùng global base
```

---

## Nguyên tắc an toàn

- **Raw là cache** (gitignored) — user xoá tuỳ ý được. URL trong `sources:` mới là
  provenance chính (host bên thứ ba, không mất theo folder local).
- **AI proposes, human decides.** Ghi thứ re-derivable (index, log) → tự làm. Assertion
  sự thật → `.proposals/` chờ người `apply`.
- **Contradiction = báo người**, không materialize thành edge, không tự chọn bên đúng.
- **Provenance bắt buộc.** Mọi claim có `[[wiki page]]` trong body hoặc URL trong `sources:`.
- **Copied-state drift.** Page không chứa value hay đổi (SHA, mtime, count tuyệt đối) —
  nằm trong frontmatter hoặc đọc live từ tooling.
- **Không ghi ngoài wiki.** Path đề xuất/proposal được chuẩn hoá và chặn lọt ra ngoài
  `wiki/` của wiki đang chỉ định.

## Giới hạn đã biết

- `wiki/log.md` **vẫn là một page** → vẫn xuất hiện trong `bm25_page`; chỉ phần *chunk* của
  nó bị loại. Hướng xử lý: `[retrieval] exclude_from_index` (`docs/tier3-roadmap.md` §3b).
- Eval mới đo trên **một wiki**; đường gộp cross-wiki của MCP chưa có metric riêng.
- `[models]` là **hợp đồng trên giấy**: Python không gọi LLM. Headless ingest
  (cron/watch không cần AI tool) chưa làm — roadmap §11.
- Chưa có test tự động cho installer/skill distribution; kiểm chứng hiện tại là chạy thật
  trên sandbox (`HOME` + `LLM_WIKI_REGISTRY` giả) và trên 2 wiki thật.
- `pages.embedding` vẫn được ghi nhưng RRF không đọc (chỉ `fusion="weighted"` dùng) →
  ứng viên bỏ nếu không ai rollback.

---

## Cross-platform

- macOS, Linux, Windows: full support (symlink có fallback copy trên Windows).
- MCP config: macOS `~/Library/Application Support/`, Linux `$XDG_CONFIG_HOME`
  (default `~/.config/`), Windows `%APPDATA%`. Riêng Command Code dùng `~/.commandcode/`.
- Skills: bản canonical nằm ở `.agents/skills/` (mọi tool theo chuẩn Agent Skills đọc
  được); client không theo chuẩn nhận symlink, hoặc bản copy nếu OS không cho symlink.

## Phát triển

```bash
pip install -e .                # CLI venv
llm-wiki base install           # sync src/llm_wiki/base_tools → ~/.llm-wiki-base/tools/
llm-wiki base install --force   # tạo lại venv base (khi requirements đổi)
```

Source layout: `src/llm_wiki/` (CLI + installer + registry), `src/llm_wiki/base_tools/`
(chạy trong base venv, **không** import package), `src/llm_wiki/base_rag/`,
`src/llm_wiki/skills/{wiki,codebase}/` (nguồn để init copy), `src/llm_wiki/templates/`.

⚠️ `src/llm_wiki/config_file.py` và `src/llm_wiki/base_tools/config_file.py` **phải khớp
key-for-key** (bản thứ hai là fallback khi tools/ chạy trong base venv không có package).
`llm-wiki doctor` so `tools/` với package và báo khi lệch.

---

Tài liệu chi tiết: schema cho agent
([`src/llm_wiki/templates/agents/_schema.md`](src/llm_wiki/templates/agents/_schema.md)) ·
runbook wiki ([`…/AGENTS.md`](src/llm_wiki/templates/agents/AGENTS.md),
[`…/CLAUDE.md`](src/llm_wiki/templates/agents/CLAUDE.md)) ·
init guide ([`docs/init.md`](docs/init.md)) · roadmap
([`docs/tier3-roadmap.md`](docs/tier3-roadmap.md)) · lịch sử phiên
([`docs/session/`](docs/session/)) · ghi ơn
([`docs/credits.md`](docs/credits.md)).

Sơ đồ động: [`docs/wiki-flow.html`](docs/wiki-flow.html)
