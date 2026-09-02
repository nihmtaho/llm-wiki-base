# llm-wiki

LLM-maintained wiki — compile knowledge 1 lần, maintain mãi. Union retrieval (BM25 page + BM25 chunk + vector, RRF fusion) có eval harness, MCP bridge, multi-base init (personal/project).

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
| **Skills** | `llm-wiki-{ingest,query,lint,reindex,review,consolidate,translate}` | cùng bộ + `llm-wiki-research` ở root repo |
| **Skill location** | `<wiki>/.agents/skills/` (per-wiki) | `<wiki>/.agents/skills/` + `<root>/.agents/skills/` (research) |

2 base dùng chung tên skill — khác nhau ở `[wiki].profile`, không ở bộ skill. MCP là centralized (`llm-wiki-base-mcp`),
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
├── tools/                           #   ingest.py, lint.py, watch.py, search.py, chunking.py, eval.py, mcp_base_server.py, db.py, ...
├── rag/                             #   embeddings.py, index.py, search.py
├── scripts/                         #   extract_url.py, extract_pdf.py, extract_youtube.py
├── templates/                       #   eval-golden.toml (cho `tools/eval.py --init`)
├── .venv/                           #   1 Python venv cho mọi wikis
├── registry.toml                    #   centralized MCP: wiki name → path/type
└── requirements.txt

my-wiki/                             # Per-wiki data (1 folder = 1 wiki)
├── .agents/skills/                  #   7 skill wiki-scoped (+ .llm-wiki-skills.json manifest)
│   ├── llm-wiki-ingest/SKILL.md
│   ├── llm-wiki-query/SKILL.md
│   ├── llm-wiki-lint/SKILL.md
│   ├── llm-wiki-reindex/SKILL.md
│   ├── llm-wiki-review/SKILL.md
│   ├── llm-wiki-consolidate/SKILL.md
│   └── llm-wiki-translate/SKILL.md
├── raw/                             #   inbox/ + cache (gitignored, có thể xoá)
├── wiki/                            #   markdown + .wiki.db + .proposals/
│   ├── index.md                     #     top-level TOC (reserved — không chunk)
│   ├── log.md                       #     append-only reverse-chronological (reserved — không chunk)
│   ├── .wiki.db                     #     SQLite: pages + pages_fts + chunks_fts
│   ├── .proposals/                  #     staging cho human-gated edits
│   ├── pins.yml                     #     sửa tay của human (survives regenerate, optional)
│   ├── alerts/                      #     hàng đợi gap từ review skill (optional)
│   └── <domain>/                    #     N domain, mỗi domain có index.md + entity/concept/source/task/
├── eval/                            #   đo chất lượng retrieval
│   ├── golden.toml                  #     query vàng (dữ liệu — COMMIT)
│   └── results.json                 #     lịch sử đo (gitignored)
├── rag/.rag_index/                  #   chunk embeddings (binary, per-wiki)
├── .env                             #   runtime paths (gitignored)
└── .llm-wiki.toml                   #   behavior config: retrieval/eval/review/lifecycle/lint/translate (commit)
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
llm-wiki init personal --name "My Knowledge" --lang vi
llm-wiki init personal -c claude -c opencode -c commandcode   # MCP clients
llm-wiki init personal --mcp-scope project        # .mcp.json ở repo thay vì config cá nhân
llm-wiki init personal --no-mcp                  # skip centralized MCP
llm-wiki init personal --no-register             # không ghi registry.toml (test/script)
llm-wiki init personal --skills-target claude    # + symlink .claude/skills/
llm-wiki init personal --skills-target both      # + .opencode/commands/
llm-wiki init personal --no-skills               # skip skill install

# Project wiki (data + centralized MCP + registry + skills 2 scope)
llm-wiki init project -c claude -c opencode
llm-wiki init project --wiki-dir project-wiki    # subfolder name
llm-wiki init project --lang vi
llm-wiki init project --mcp-scope project        # .mcp.json tại root repo (commit được)
llm-wiki init project --no-mcp                   # skip centralized MCP
llm-wiki init project --server-name my-wiki-mcp  # custom centralized server name
llm-wiki init project --no-register              # tránh làm bẩn registry khi test
```

Client chấp nhận: `claude`, `opencode`, `zed`, `commandcode`. `--mcp-scope project`
chỉ có tác dụng với `claude`/`commandcode` (`<root>/.mcp.json`, key `mcpServers`);
opencode/zed chỉ có user scope. Init in ra **đường dẫn file vừa ghi + key + scope**.

### Wiki management (centralized MCP registry)

```bash
llm-wiki wiki list                           # name + id + path + type
llm-wiki wiki add my-wiki /path/to/wiki --type personal  # register existing wiki
llm-wiki wiki remove my-wiki                 # unregister (files không bị xóa); accept id
```

Mỗi wiki có `name` (key tra cứu, dễ đọc — dùng làm tham số `wiki=`) và `id` (UUID
máy sinh, ổn định). Trùng `name` mà khác path → init **tự thêm hậu tố `-<uuid8>`**
thay vì đá wiki cũ khỏi registry im lặng. Param `wiki=` của MCP accept cả hai.

### Per-wiki operations (cwd = wiki dir)

```bash
llm-wiki ingest raw/inbox/foo.md   # index 1 source vào search DB
llm-wiki reindex                    # index tăng dần theo content-hash (+ chunks_fts)
llm-wiki reindex --check            # dry-run: báo sẽ index/xoá gì + config drift + trạng thái chunk index
llm-wiki reindex --full             # rebuild toàn bộ (sau khi đổi embed_model/chunk_tokens/vector/fusion)
llm-wiki lint                       # health check deterministic (orphan, broken link, frontmatter, ...)
llm-wiki lint --fix                 # xoá dangling rows + thêm index entries (additive)
llm-wiki eval                       # đo retrieval trên query vàng: P@k / R@k / MRR (read-only)
llm-wiki eval --compare             # so tier1-weighted / rrf-text / rrf+vector + verdict bật vector
llm-wiki eval --init                # tạo eval/golden.toml từ template
llm-wiki proposals list             # đề xuất của AI đang chờ duyệt (+ độ lớn diff)
llm-wiki proposals show <name>      # metadata + unified diff so với page hiện tại
llm-wiki proposals apply <name> [--by <human-id>]   # ghi vào page + log + reindex + xoá proposal
llm-wiki proposals discard <name> --force           # từ bỏ proposal
llm-wiki proposals new -t wiki/x/y.md -f body.md    # tạo proposal từ CLI (cùng format MCP)
llm-wiki config show                # xem effective config (defaults + TOML + env override)
llm-wiki verify wiki/<domain>/concept/x.md --by <human-id>   # human duyệt (set verified)
llm-wiki verify <path> --unverify   # xoá verified (hạ về unverified)
llm-wiki watch                      # daemon: scan inbox → ingest → reindex → lint (+ nhắc review due)
llm-wiki doctor                     # kiểm môi trường + nói rõ việc gì cần AI tool
```

`llm-wiki doctor` check: base runtime, `tools/` có lệch với package không (báo
`llm-wiki base install`), deps trong base venv (`mcp`, `fastembed`, `tomli`),
registry (path ma, wiki thiếu id), wiki hiện tại (có `.llm-wiki.toml`, có
`[wiki].profile`, đã đăng ký chưa, còn proposal tồn đọng), và cuối cùng là bảng
**việc bắt buộc có AI tool** — vì `llm-wiki` không gọi LLM: nó làm phần tất định,
còn ingest-ra-page / review / consolidate / translate / rerank là skill.
FAIL → exit 1; WARN → vẫn 0.

### Translation

```bash
llm-wiki translate enable --lang vi --lang ja   # ghi vào .llm-wiki.toml
llm-wiki translate status                        # xem trạng thái
llm-wiki translate disable                       # disable (giữ langs)
llm-wiki translate check --lang vi               # verify đồng bộ
```

---

## Skills

8 skill, **không còn chia tên personal/project** — chế độ đọc từ `[wiki].profile`
(`personal` | `codebase`) trong `.llm-wiki.toml`. Cài đặt khi `llm-wiki init`, chia 2 scope:

| Skill | Scope | Vai trò |
|---|---|---|
| `llm-wiki-ingest` | wiki | raw → source/entity/concept page + cross-link + index/log + reindex |
| `llm-wiki-query` | wiki | trả lời từ **wiki đang đứng**: retrieval → rerank → cite → file synthesis |
| `llm-wiki-lint` | wiki | health-check TẤT ĐỊNH: orphan, broken link, frontmatter, index sync |
| `llm-wiki-reindex` | wiki | dựng/chẩn đoán chỉ mục derived: `--check`, `--full`, lệch kênh |
| `llm-wiki-review` | wiki | Health-check SINH SINH: mâu thuẫn, stale, trust gap → `wiki/alerts/` |
| `llm-wiki-consolidate` | wiki | Gộp log/mẩu rải rác → concept canonical (additive, distill-verify) |
| `llm-wiki-translate` | wiki | Dịch page sang `[translate].langs` (dùng LLM của AI tool) |
| `llm-wiki-research` | **codebase root** | Research **xuyên nhiều wiki** qua centralized MCP + đối chiếu personal ↔ project |

`llm-wiki-research` cài ở `<root_repo>/.agents/skills/` chứ **không** nằm trong wiki:
nó cần thấy mọi wiki, còn skill wiki-scoped chỉ lo một wiki.

**Phân phối:** `.agents/skills/` là bản canonical duy nhất.

| `--skills-target` | kết quả |
|---|---|
| `universal` (default) | copy vào `.agents/skills/` + symlink cho client được chọn qua `-c` |
| `claude` | như trên + chắc chắn link `.claude/skills/` |
| `both` | link cả `.claude/skills/` và `.opencode/commands/` |
| `skip` | không cài (`--no-skills`) |

- **Command Code** đọc `.agents/skills/` (project) và `~/.agents/skills/` (user) trực tiếp → không cần link; tạo `.commandcode/skills/` sẽ bị ưu tiên cao hơn và sinh cảnh báo trùng tên.
- **Claude Code**: dir symlink `.claude/skills/<name>` → `.agents/skills/<name>`.
- **OpenCode**: file symlink `.opencode/commands/<name>.md` → `.agents/skills/<name>/SKILL.md`.
- Windows không có quyền symlink → tự fallback sang copy.

**Prune:** skill đổi tên/gộp ở bản cũ (`wiki-project-*`) bị xoá khi re-init, nhưng chỉ
những thứ do llm-wiki cài (ghi danh trong `.agents/skills/.llm-wiki-skills.json`) —
skill bạn tự viết cùng folder được giữ nguyên.

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

## Config (.llm-wiki.toml)

Behavior config per-wiki, **commit** vào wiki repo (init tự tạo template). Precedence: env var > TOML > builtin default.

```toml
[wiki]
profile = "personal"      # personal | codebase — skill đọc để chọn chế độ (init set đúng)
lang = "en"               # ngôn ngữ agent VIẾT page (không phải đích dịch)

[retrieval]
fusion = "rrf"            # "weighted" = hành vi cũ: rollback 1 dòng, cũng là baseline A-B
chunk_bm25 = true         # kênh BM25 trên semantic chunks
vector = true             # bật mặc định từ 2026-09-02 (đo được); tắt nếu eval của chính wiki không cho Δ>0
rerank = "llm"            # skill layer rerank (Python không đọc key này)
chunk_tokens = 512        # chunk theo section (~token*4 chars)
top_k_bm25 = 20           # ứng viên mỗi kênh text
top_k_vector = 20         # ứng viên kênh vector
top_n_final = 8           # kết quả cuối + budget đọc của skill
relax_recall = true       # giữ nguyên → AND sanitize → OR một lần (CJK-safe)

[retrieval.weights]       # RRF chỉ nhạy tỉ số
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

Đổi `embed_model`/`chunk_tokens`/`vector`/`fusion` → chạy `llm-wiki reindex --full`. Runtime plumbing (đường dẫn) vẫn qua `.env` + env vars.

`llm-wiki init` bật sẵn `vector = true` trong template (có bằng chứng đo, ghi ngay trong comment của file). Hai key `chunk_tokens` và `rrf_k` **đã đo là không có tác dụng** trên wiki nhỏ (256/512/1024 cho cùng số chunk khi mọi section đều ngắn; sweep `rrf_k` 20→250 cho số liệu giống hệt) — đừng đổi chúng cho đến khi eval của chính wiki bạn chỉ ra khác biệt.

Env override: `WIKI_EMBED_MODEL`, `WIKI_FUSION`, `WIKI_CHUNK_BM25`, `WIKI_BM25_WEIGHT`, `WIKI_VEC_WEIGHT` (2 cái cuối chỉ chi phối khi `fusion = "weighted"`). Installer **không** pin chúng vào MCP entry nữa — pin ở đó làm `.llm-wiki.toml` bị vô hiệu trong MCP (env > TOML) nhưng CLI vẫn đọc, tức cùng wiki ra hai kết quả khác nhau.

---

## Retrieval & eval

**Union retrieval + RRF** (`wiki_search` / `tools/search.py`): 3 kênh xếp hạng độc lập rồi gộp bằng **reciprocal rank fusion trên hạng** — không cộng thẳng score vì `bm25()` và cosine khác thang hoàn toàn.

| kênh | hạ tầng | ghi chú |
|---|---|---|
| `bm25_page` | FTS5 `pages_fts` (wiki + raw) | luôn chạy |
| `bm25_chunk` | FTS5 `chunks_fts` trong `.wiki.db` | bắt được term hiếm nằm sâu trong page dài |
| `vector_chunk` | `rag/.rag_index/{chunks.json,vectors.npy}` | chỉ khi `vector = true` |

Mỗi kết quả có `matched_by` (kênh nào tìm ra) + `rank` + `snippet` (có thể là **text của một chunk** → đủ để CHỌN page, không đủ để trả lời). Chunk của 2 kênh dùng chung `tools/chunking.py` nên cùng ranh giới; `index.md`/`log.md` (reserved), bản dịch `*.lang.md`, frontmatter và footnote verbatim **không** được chunk.

**Rerank ở skill layer** (`[retrieval].rerank = "llm"`): skill xin `top_k` rộng hơn (`2 × top_n_final`), chấm ứng viên bằng title/snippet/`matched_by`, rồi mới mở `top_n_final` page. Không thêm reranker model vào code.

**Fallback tất định**: thiếu model / chưa build chunk → từng kênh tự tắt, vẫn chạy BM25. "Không model" ≠ "hỏng".

**Đo, đừng đoán**:

```bash
llm-wiki eval --init          # tạo eval/golden.toml (đó là dữ liệu — COMMIT)
llm-wiki eval                 # P@k / R@k / MRR theo config hiện tại
llm-wiki eval --compare       # tier1-weighted / rrf-text / rrf+vector + verdict
llm-wiki eval --compare -v    # thêm số liệu từng query
```

`eval/golden.toml` chứa query thật + danh sách concept chấp nhận được; eval sẽ cảnh báo `relevant path KHÔNG khớp page nào trong DB` thay vì âm lặng tính điểm sai. Kết quả append `eval/results.json` (gitignored) kèm fingerprint config để so sánh theo thời gian. `zero_recall_queries` = wiki thiếu tài liệu (việc của ingest), không phải retriever dở. Nếu một kênh chết **vì lỗi**, eval in `[ERROR] kênh bị tắt vì lỗi` — vì số liệu của profile đó khi đó là giả.

Điều kiện bật vector: ΔR@k của profile `+vector` dương rõ rệt trên bộ query vàng của *chính wiki đó*. Template mới bật sẵn `vector = true` vì có bằng chứng đo (dưới); wiki cũ nâng cấp vẫn `false` cho tới khi bạn tự `eval --compare`. Ở scale rất nhỏ (< ~50k token) BM25 thường đã đủ.

**Cái bẫy đã đo được của RRF** (trên một wiki thật, 18 query / 21 page): với weight bằng nhau, page đứng hạng *giữa ở cả hai* kênh (đồng thuận) có thể bị page hạng 1 ở một kênh + hạng 11 ở kênh kia chèn mất ngay sát cutoff — text-only RRF vì thế **mất** một query mà weighted-sum cũ tìm ra. Hai đòn bẩy, đo ra:

- `rrf_k` **không phải** đòn bẩy: sweep 20 → 250 cho số liệu giống hệt nhau trên corpus này.
- `[retrieval.weights].bm25_page = 2.0` cứu lại query đó (R@8 bằng vector) nhưng **MRR tụt** dưới cả rrf-text → chỉ dùng khi không muốn bật vector.
- `vector = true` cho cả recall lẫn first-hit tốt nhất trong phép đo đó (kênh vector bắt được paraphrase không trùng từ, đúng case mà text fail).

Tóm lại: RRF tốt hơn weighted-sum về *độ phủ*, không tự động tốt hơn về *first hit*. Đó là lý do có eval harness thay vì tin vào lý thuyết rank-fusion.

**Limitation đã biết**: `wiki/log.md` vẫn là một *page* (nên vẫn xuất hiện trong `bm25_page`); chỉ phần *chunk* của nó bị loại. Hướng xử lý sau này: `[retrieval] exclude_from_index` (xem `docs/tier3-roadmap.md`).

---

## Nâng cấp từ bản trước

```bash
pip install -e . && llm-wiki base install         # 1. sync code → ~/.llm-wiki-base/
cd <wiki-cũ> && llm-wiki reindex --full           # 2. build chunks_fts + sửa FTS duplicate rows
cd <wiki-cũ> && llm-wiki init personal -c claude  # 3. refresh skills + MCP env (trả lời yes)
llm-wiki doctor                                   # 4. kiểm còn thiếu gì
```

- Bước 2 bắt buộc một lần: incremental reindex bỏ qua page không đổi content-hash, nên wiki cũ sẽ không bao giờ có chunk nếu không `--full`.
- Bước 3: `init` **không** ghi đè `.llm-wiki.toml` (guard exists) → cấu hình của bạn giữ nguyên, key mới tự lấy default; nhưng skills là bản copy nên cần refresh.
- **Skills đổi tên + gộp** (bản này): 13 skill personal/project → 8 skill `llm-wiki-*` profile-aware. Re-init sẽ **tự xoá** `wiki-project-*` cũ và giữ skill bạn tự viết. Project wiki còn nhận thêm `llm-wiki-research` ở **root repo**.
- **Wiki bật `vector = true` mặc định** (template mới). Wiki cũ giữ `false` cho tới khi bạn `eval --compare`; đổi sang true thì `reindex --full` để dựng `rag/.rag_index`.
- Registry có thêm **`id` (UUID)** cho mỗi wiki; `wiki add`/`init` lại sẽ gán. Trùng tên khác path không còn đá nhau im lặng.
- `llm-wiki init` có `--no-register` (và env `LLM_WIKI_REGISTRY`) để test không ghi vào registry thật.
- Thứ tự rank của `wiki_search` **đổi** so với bản trước (RRF thay weighted sum). Muốn hành vi cũ: `fusion = "weighted"` trong `.llm-wiki.toml`.
- `semantic_search` không còn trả chunk của `index.md`/`log.md` (chủ đích).
- Code cũ vẫn mở DB mới bình thường (`chunks_fts` chỉ bị code mới đọc).
- `llm-wiki proposals list|show|apply|discard` là lệnh mới để duyệt `wiki/.proposals/`; proposal cũ (không metadata) cần `apply --target <path>` tường minh.

---

## Verify & trust tier

Mỗi page có `generated: {by, at}` (ai sinh) và tùy chọn `verified: {by, at}`:

- **unverified** — không có `verified` (mặc định khi AI viết).
- **human-reviewed** — `verified.by = "human:<id>"`. Duyệt = set verified, dùng chung personal + project:

```bash
llm-wiki verify wiki/<domain>/concept/x.md --by <human-id>
llm-wiki verify <path> --unverify   # hạ về unverified
```

AI KHÔNG tự set `verified`. Human sửa tay quan trọng → ghi vào `wiki/pins.yml` (claim + anchor heading) — ingest/consolidate không ghi đè section mà pin bám vào; mâu thuẫn → `wiki/alerts/`.

---

## MCP bridge

MCP = cầu nối cho AI tool, **KHÔNG** viết thẳng wiki:

| Tool | Vai trò |
|---|---|
| `wiki_search(query, top_k, wiki)` | **Union retrieval + RRF**: `bm25_page` ∪ `bm25_chunk` ∪ `vector_chunk`; mỗi kết quả có `matched_by` + `rank` + `snippet` (có thể là chunk text). `top_k` = kết quả cuối, `0` = theo `top_n_final` |
| `semantic_search(query, top_k, wiki)` | Chunk-level vector search thô (chỉ để tìm concept, không phải nguồn trả lời) |
| `wiki_read(path, wiki)` | Đọc 1 file |
| `wiki_list(domain, kind, wiki)` | Liệt kê pages, filter |
| `list_raw_source(subdir, wiki)` | Liệt kê files trong raw/ |
| `read_raw_source(name, subdir, wiki)` | Đọc raw source |
| `wiki_submit(title, content, wiki, ...)` | **Ghi vào `raw/inbox/`** (KHÔNG wiki) |
| `wiki_propose_edit(path, content, wiki)` | Staging vào `wiki/.proposals/` |
| `wiki_lint(wiki)` | Health-check |

Rerank **không phải MCP tool** — đó là bước LLM trong skill `llm-wiki-query` /
`llm-wiki-research` (xem `[retrieval].rerank`).

**Cài MCP cho client** (`llm-wiki init -c ...`):

| client | user scope | project scope | key |
|---|---|---|---|
| `claude` | `<AppSupport>/claude/mcp_servers.json` (fallback `~/.claude/`) | `<root>/.mcp.json` | `mcpServers` |
| `commandcode` | `~/.commandcode/mcp.json` | `<root>/.mcp.json` | `mcpServers` |
| `opencode` | `<AppSupport>/opencode/opencode.json` (fallback `~/.opencode/`) | không có | `mcp` |
| `zed` | `<AppSupport>/Zed/settings.json` (fallback `~/.zed/`) | không có | `context_servers` |

`--mcp-scope project` ghi entry vào `.mcp.json` ở root repo để cả team dùng qua VCS.
Installer không pin env retrieval nào vào entry (env > TOML, pin sẽ làm
`.llm-wiki.toml` của wiki vô hiệu riêng trong MCP).

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
