# Session — Tier 3 đợt 2: skills + MCP clients + config + naming + proposals

**Ngày**: 2026-09-02 (tiếp ngay sau `session-tier3-retrieval-2026-09-02.md`)
**Nguồn việc**: `docs/human-ideas/improve/tasks.md` (4 nhóm: Skills / CLI+MCP / Config+đặt tên / Cleanup)
**Plan**: không qua plan mode — người dùng yêu cầu "tiếp tục thực hiện các task"; 4 ngã rẽ
thiết kế được hỏi trực tiếp (`ask_user_question`) và cả 4 chọn phương án khuyến nghị.
**Trạng thái**: đã implement, đã verify trên 2 wiki thật, **đã commit**.

---

## 1. Quyết định chính (và cái bị từ chối có chủ đích)

| ngã rẽ | quyết định | lý do |
|---|---|---|
| Bộ skill cuối | **8 skill** `llm-wiki-*` profile-aware: ingest, query, lint, reindex, review, consolidate, translate, research | `tasks.md` ghi "6 skill" nhưng `translate`/`plan`/`mcp` không nằm trong 6 tên đó. `plan` gộp vào `query`+`research` (trùng ~80% và hardcode `~/.commandcode/plans/` → vỡ trên client khác). `mcp` (doc tham chiếu) gộp vào `research`. `translate` GIỮ vì 104 dòng + có CLI `translate check` |
| Canonical skill dir | `.agents/skills/` là bản duy nhất; claude/opencode nhận **symlink trỏ vào đó** | Layout cũ copy vào `.claude/skills/` rồi link ngược (trái chiều với README) → mỗi lần upgrade phải sửa 2 nơi. Lỗi này nằm trong `_skills.py` cũ, không ai phát hiện cho tới lúc đọc lại |
| `link_skills.sh` | **xoá**, port sang `_skills.link_clients()` (Python) | Script là code chết (0 call-site), tính `REPO_ROOT` theo vị trí chính nó nên sau `base install` nó trỏ vào `~/.llm-wiki-base/.agents/skills/` — thư mục không tồn tại. Python bản mới chạy trên Windows (fallback copy) + có prune. `installer.install_skill()` (cũng 0 call-site) bị xoá theo để lại MỘT chỗ định nghĩa layout client |
| commandcode skill link | **không tạo** `.commandcode/skills/` | Command Code đọc `.agents/skills/` (project) và `~/.agents/skills/` (user) trực tiếp; `.commandcode/skills/` lại ưu tiên CAO hơn → tạo ra là tự chuốc cảnh báo "Duplicate names" khi hai bản lệch |
| Providers (`tasks.md` 3) | chỉ **schema** `[models]` + doc, KHÔNG viết LLM client | Mâu thuẫn trực tiếp với nguyên tắc "dependency-averse core" của repo. Headless ingest là quy trình nhiều bước, không phải 1 lần call API → ghi thành §11 roadmap, kèm gợi ý bắt đầu từ `translate` (đã có `translate check` để nghiệm thu) |
| Đặt tên wiki | giữ `name` human-readable + thêm `id` UUID; trùng tên khác path → tự thêm `-<uuid8>` | `name` là tham số `wiki=` con người phải gõ; phương án `name = slug-uuid` luôn luôn làm MCP tool khó dùng. Still satisfies "user-name + UUID" qua `id` |
| `.proposals` (`tasks.md` 4) | sửa **root cause**: metadata target + CLI `list/show/apply/discard/new` | File duy nhất trên đĩa không "dư thừa" — nó chứa correction đã verify (import path `SplitView` sai) mà page thật vẫn đang sai. Lý do nó mục rữa: không có lệnh nào để xem/duyệt, và tên file chỉ giữ `basename` nên mất thông tin đích |

---

## 2. Implement theo mảng

### 2.1 Skills — gộp + phân phối (Task 1)

- Cây mới: `src/llm_wiki/skills/wiki/<7 skill>` + `src/llm_wiki/skills/codebase/llm-wiki-research`.
  Xoá `skills/personal/` và `skills/project/`. **790 dòng / 13 file → 584 dòng / 8 file (−26%)**
  mà vẫn thêm được skill `reindex` mới và hấp thụ `plan` + `mcp`.
- Mỗi skill có bảng/marked `**[personal]**` / `**[codebase]**`; nguồn chế độ là
  `[wiki].profile` (mới — xem 2.4). `llm-wiki-query` vs `llm-wiki-research` có bảng ranh
  giới ngay đầu file: *query = một wiki đang đứng (được phép ghi synthesis)*,
  *research = xuyên wiki (chỉ staging)*.
- `src/llm_wiki/_skills.py` viết lại:
  - `install_skills(root, target, subset, clients)` — `subset`: `wiki` | `codebase` | `all`;
    `target` lạ giờ **raise ValueError** (trước đây âm thầm trả `[]` rồi init in
    "skills source not found" — thông điệp sai lệch).
  - `link_clients()` — dir symlink cho claude, flat `<name>.md` symlink cho opencode,
    prune link chết, **không** đụng real dir/file lạ (kiểm bằng `_is_ours()`: nội dung
    có khớp bản `.agents/` không).
  - `_prune()` — chỉ xoá thứ (a) mang prefix cũ `wiki-project-`/`llm-wiki-project-` hoặc
    (b) có tên trong manifest `.agents/skills/.llm-wiki-skills.json`. Skill user tự viết
    cùng folder được giữ (đã test).
  - Sửa bug tự mắc trong lúc viết: `_prune` đọc manifest **sau khi** `_copy_subset` ghi
    đè → không còn danh sách cũ; phải đọc trước khi copy.

### 2.2 MCP — client + scope + in vị trí (Task 2a)

- `src/llm_wiki/config.py`: thêm `commandcode` (`home_dir` riêng vì nó KHÔNG dùng
  XDG/App Support) + `project_mcp` per-client + `supports_project_scope()` + `mcp_key()`.
  `opencode`/`zed` khai rõ `project_mcp = None` (không có project-scope MCP file nào trong
  convention của chúng — không bịa).
- `src/llm_wiki/installer.py`:
  - `McpInstall` dataclass (client, path, key, scope, server_name) với `describe()` in
    một dòng đủ: `path [scope: giải nghĩa] key=mcpServers.llm-wiki-base-mcp`.
  - `_build_mcp_entry` thêm shape commandcode: `{transport:"stdio", enabled:true,
    command, args, env}` — **không có `cwd`** (schema của nó không nhận; server vẫn chạy
    vì command/args là absolute và base dir truyền qua `LLM_WIKI_BASE_DIR`).
  - `install_mcp_config` giờ báo lỗi có ngữ cảnh khi file config JSON hỏng / key không
    phải object, thay vì `json.loads` ném traceback rồi bị caller bắt thành `✗ {e}`.
  - Xoá `install_skill()` (dead code, trùng năng lực với `link_clients`).
- `init personal|project`: cờ `--mcp-scope user|project`; project wiki cài skills ở **2
  scope** (wiki-dir + root repo); tổng kết in từng client với `describe()`; nếu cài MCP
  lỗi thì in thẳng "LỖI với X — chạy lại init (idempotent)" thay vì im lặng exit 0.
- Wizard `llm-wiki init` hỏi scope và giải thích 2 lựa chọn.

### 2.3 CLI — lỗi rõ + doctor (Task 2b)

- `_run_base_tool()` (cổ chai của 6 lệnh data): `check_call` → `subprocess.run(check=True)`
  bọc `CalledProcessError` → message tiếng Việt + exit code của tool (trước đây traceback
  thô). Thêm check thiếu venv python. Bỏ `SystemExit` → `typer.Exit`.
- `llm-wiki doctor` (mới, `cli.py`): kiểm base runtime, **`tools/` lệch với package**
  (so byte-for-byte từng file trong `base_tools/` → nhắc `llm-wiki base install`),
  deps trong base venv (`mcp`, `fastembed`, và `tomli` CHỈ khi venv < 3.11),
  registry (path ma → FAIL; thiếu id → WARN), wiki hiện tại (`.llm-wiki.toml`,
  `[wiki].profile`, đã đăng ký chưa, proposal tồn đọng), rồi bảng **6 việc bắt buộc có
  AI tool**. FAIL → exit 1.
- `llm-wiki proposals` (mới) — xem 2.5.

### 2.4 Config + đặt tên (Task 3)

- `[wiki]` section mới: `profile` (personal|codebase) + `lang`. `init project` **ép**
  `profile = "codebase"` sau khi copy template (template mang giá trị personal) qua
  `config_file.ensure_wiki_identity()`.
- `vector` mặc định **true** ở cả 3 chỗ (`config_file.DEFAULTS`, bản shim trong
  `base_tools/config_file.py`, template) kèm comment ghi số liệu đo được + điều kiện tắt.
  Bản shim giờ có chú thích "PHẢI KHỚP KEY-FOR-KEY" + `doctor` là máy phát hiện lệch.
- **`[models]`** (`light`/`heavy`/`provider`/`api_key_env`) — schema + doc chỉ; Python
  không đọc. `api_key_env` là TÊN biến env, không bao giờ ghi key thẳng vào file.
- `config_file.set_translate()` trước đây parse-then-dump `tomli_w` → **mọi comment
  trong `.llm-wiki.toml` bốc hơi khi chạy `llm-wiki translate enable`**, kể cả block
  bằng chứng vector. Viết helper `_upsert_toml_keys()` sửa đúng dòng của key được yêu
  cầu; `set_translate` + `ensure_wiki_identity` đi qua nó. Test: 50 → 50 dấu `#`, parse OK.
- `registry.py`: `id` (uuid4 hex 12), `_backfill_ids` (wiki cũ được gán id khi save),
  `add_wiki` trả **name thật đã dùng** (khác name xin vào khi trùng), `find()` tra theo
  name trước rồi id, `remove_wiki` accept cả hai. `mcp_base_server._wiki_entry` accept
  cả id. `--no-register` + env `LLM_WIKI_REGISTRY` (đóng follow-up §8.5 của session trước).
- **Đo trước khi đổi default** (`tasks.md` 3 "tối ưu config mặc định") — chạy trên
  COPY của wiki-test trong scratchpad, wiki thật không bị đụng:

  | biến | kết quả đo | kết luận |
  |---|---|---|
  | `chunk_tokens` 256 / 512 / 1024 | **28 chunk cả ba**, P@8/R@8/MRR giống hệt từng chữ số | không có bằng chứng để đổi; key chỉ tác dụng khi một section dài hơn nó. Ghi thẳng vào comment template |
  | `top_n_final` 4 / 8 / 12 | rrf+vector: R .8981 / .9722 / 1.0 nhưng P .3611 / .1944 / .1343 | giữ 8; k=12 mua 0.028 recall bằng 30% context |
  | `vector` | R@8 .9167 → .9722, MRR .8518 → .8981 (18 query) | đổi mặc định, có số liệu |

### 2.5 Proposals (Task 4)

- `src/llm_wiki/base_tools/proposals.py` (mới, 382 dòng): `list` / `show` (unified diff)
  / `apply` / `discard` / `new` + `stage()` là **entry point duy nhất** để ghi proposal —
  cả hai MCP server (`mcp_base_server`, `mcp_server` legacy) gọi chung, hết cảnh hai bản
  sao chép logic đặt tên file.
- Format: header `<!-- llm-wiki-proposal\n target: …\n wiki: …\n created: ISO\n by: …\n
  note: …\n-->` rồi tới nội dung nguyên văn. HTML comment để renderer ẩn nó, và để
  frontmatter của page được đề xuất vẫn là frontmatter thật.
- `apply`: ghi page + insert entry `wiki/log.md` (reverse-chronological, không rewrite
  cả file) + reindex trực tiếp qua `search.index_file_at` + xoá proposal + in dòng máy
  đọc được `APPLIED\t<rel>` (CLI cần nó vì sau apply thì proposal không còn trên đĩa).
  `--by <human-id>` được xử lý ở CLI (gói `llm_wiki.verify.set_verified`) vì tools/ chạy
  trong base venv không import được package — không duplicate logic verify.
- **Phân biệt rõ đoán vs khai**: `resolve_dest()` cho phép đoán target từ `basename` để
  `list`/`show` hiển thị diff của proposal CŨ; `apply` thì KHÔNG dùng đoán — bắt buộc
  metadata hoặc `--target` tường minh, vì đoán sai là ghi đè page thật.

---

## 3. Bug tìm ra trong lúc làm (tất cả đều do chạy, không do đọc code)

1. `doctor` đòi `tomli` trên base venv Python **3.14** → FAIL giả. `tomllib` ở stdlib từ
   3.11; giờ dò version bằng chính base python rồi mới kiểm.
2. Rich **ăn mất `[wiki]`** trong chuỗi in ra (`✓ .profile = personal` mất chữ `[wiki]`)
   → phải escape `\\[wiki\\]`. Gặp ở cả doctor lẫn 2 init module.
3. `reindex --full` xong vẫn in "chạy `llm-wiki reindex --full`" — cảnh báo drift phát
   *sau khi* meta đã được ghi, tức không còn việc gì phải làm. Giờ chỉ WARN khi
   incremental + config đổi, và nói thêm khi `vector=false` mà rag index cũ còn lệch.
4. `set_translate` phá comment (mục 2.4) — đã sửa.
5. `_prune` đọc manifest sau khi bị ghi đè → prune tên đổi không hoạt động. Sửa thứ tự.
6. `proposals list` báo "[target không tìm thấy file!]" cho proposal cũ dù đã đoán ĐÚNG
   tên file — cờ `exists` chỉ tin metadata. Tách `declared` (từ metadata) khỏi `found`
   (kể cả đoán).
7. `_target_from_apply_output()` (bản nháp đầu) gọi `proposals show` SAU khi apply đã xoá
   file → luôn trả None. Thay bằng dòng `APPLIED\t<rel>` trong output.
8. Hai lần lỗi sinh viên khi viết text: lẫn ký tự CJK (`把它`, `来源`, `改名`, `复用`) vào
   tiếng Việt — tự phát hiện và sửa khi đọc lại file.
9. `printf '---\n…'` trong test bị shell hiểu `--` là option (lỗi command test, không
   phải lỗi repo).

## 4. Verification — đã chạy và thấy gì

```bash
# 0. sandbox: HOME giả + registry giả, để không mutate máy
export HOME=$SCRATCH/home LLM_WIKI_BASE_DIR=$HOME/.llm-wiki-base \
       LLM_WIKI_REGISTRY=$SCRATCH/home/reg.toml
# 1. compile + không SyntaxWarning
.venv/bin/python -W error::SyntaxWarning -c "import sys;sys.path.insert(0,'src');import llm_wiki.cli"
# 2. TOML writer giữ comment
.venv/bin/python -c "... _upsert_toml_keys(template, 'wiki', {'profile':'\"codebase\"'}) ..."
# 3. init project trong sandbox → 2 scope skills + link + registry id + config entry
llm-wiki init project --root $SCRATCH/fakeproj --wiki-dir wiki -c commandcode -c claude --lang vi --force
# 4. prune an toàn:plant wiki-project-* + my-own-skill → re-init → phải còn my-own-skill
# 5. lifecycle proposals trên COPY: new → list → show → apply → log → reindex
# 6. rollout thật
cd wiki-test && llm-wiki init personal -c commandcode -c claude --force && llm-wiki doctor
cd wiki-project-test && llm-wiki init project --root . --wiki-dir wiki -c commandcode -c claude --force
cd wiki-project-test/wiki && llm-wiki reindex --full && llm-wiki doctor
```

| # | kiểm | kết quả |
|---|---|---|
| 1 | compileall + `-W error::SyntaxWarning` | PASS (không warning nào) |
| 2 | `_upsert_toml_keys` trên template | 50 → 50 dấu `#`, `profile="codebase"` đúng dòng, `tomllib.loads` parse OK, thêm section mới khi thiếu |
| 3 | sandbox `init project` | 7 skill ở `wiki/.agents/skills/`, `llm-wiki-research` ở `.agents/skills/` root; `.claude/skills/*` là symlink trỏ vào `.agents/`; registry có `id = af74b6441626`; `[wiki].profile = codebase`, `lang = "vi"` |
| 4 | commandcode entry | `{transport:"stdio", enabled:true, command, args, env}` — không `cwd`, khớp file user đang có thật trên đĩa |
| 5 | prune | xoá 7 `wiki-project-*` trên wiki thật, **giữ** `my-own-skill` (test riêng) |
| 6 | proposals lifecycle | `new` → header metadata đủ target/created/by/note; `show` diff thật; `apply` ghi page + log + `✓ indexed` + `APPLIED\t…`; `discard` không `--force` từ chối |
| 7 | proposal cũ không metadata | `list` đoán đúng `wiki/expo-router/source/split-view.md` + hiện `+15/-10`; `apply` từ chối ghi nếu không `--target` |
| 8 | rollout `wiki-test` | skills 8, registry `id = cb9342c95038`, doctor `OK — 1 cảnh báo` (proposal tồn đọng, đúng) |
| 9 | rollout `wiki-project-test/wiki` | `reindex --full` → schema 3, **11 chunks_fts**, `vector skipped` (wiki này vẫn `vector = false`), `--check` sạch, doctor OK |
| 10 | eval không hỏng | `llm-wiki eval --compare` trên wiki-test vẫn ra bộ số liệu như §5b session trước |

## 5. Files thay đổi (40 file, +2154 / −1102)

**Mới**
- `src/llm_wiki/base_tools/proposals.py` (382)
- `src/llm_wiki/skills/codebase/llm-wiki-research/SKILL.md` (89)
- `src/llm_wiki/skills/wiki/llm-wiki-{reindex,ingest,query,lint,review,consolidate}/SKILL.md` (352)
- `docs/session/session-tier3-skills-mcp-config-2026-09-02.md` (file này)

**Sửa**: `_skills.py` (viết lại), `config.py`, `installer.py`, `registry.py`,
`config_file.py` (cả bản shim `base_tools/`), `cli.py` (955 dòng: flags + proposals +
doctor + `_run_base_tool`), `init_personal.py`, `init_project.py`,
`base_tools/{reindex,mcp_server,mcp_base_server}.py`,
`templates/{llm-wiki.toml,agents/AGENTS.md,agents/CLAUDE.md}`,
`README.md`, `docs/init.md`, `docs/tier3-roadmap.md`,
`skills/wiki/llm-wiki-translate/SKILL.md` (move từ `personal/`, nội dung giữ nguyên).

**Xoá**: `skills/personal/*` + `skills/project/*` (11 file), `base_scripts/link_skills.sh`.

## 6. Trạng thái máy này (cái gì đã chạy thật, cái gì còn chờ bạn)

- **Đã chạy trên máy bạn**: `llm-wiki base install` (sync tools/ — giờ có `proposals.py`);
  `init personal` trên `wiki-test`; `init project` trên `wiki-project-test`;
  `reindex --full` trên `wiki-project-test/wiki`.
- **File config cá nhân bị ghi** (bởi init, nội dung idempotent — cùng entry đã có từ trước):
  `~/.commandcode/mcp.json`, `~/Library/Application Support/claude/mcp_servers.json`.
  Skill links tạo ở cấp project: `wiki-test/.claude/skills/`, `wiki-project-test/.claude/skills/`.
  Test MCP/skills cũng tạo file trong `HOME` **giả** (scratchpad) — không ảnh hưởng máy.
- **Còn chờ bạn**:
  1. Duyệt proposal thật đang tồn (nó sửa import path sai của `SplitView`):
     `cd ~/developer/repos/per-projects/wiki-test && llm-wiki proposals show split-view`
     rồi `llm-wiki proposals apply 20260901-214012__split-view.md --target wiki/expo-router/source/split-view.md --by <id>`
  2. Thay query AI-soạn trong `wiki-test/eval/golden.toml` bằng câu hỏi thật (§8.1 session trước).
  3. `wiki-project-test/wiki` vẫn `vector = false` — cần `eval/golden.toml` thật rồi
     `llm-wiki eval --compare` mới có cơ sở bật.
  4. Rác phát hiện được nhưng không tự xoá: `~/Library/Application Support/claude/mcp_servers.json`
     còn entry **`test-wiki4`** từ thời MCP per-wiki (đã bỏ từ lâu). Xá: `llm-wiki` không
     có lệnh xoá MCP entry — sửa tay file đó.
  5. `wiki-test` không phải git repo → `eval/golden.toml` + `results.json` + config chưa
     được track.
  6. Khởi động lại AI tool để MCP process đọc registry mới (id + `_wiki_entry` accept id).

## 7. Ghi chú vận hành

- **Skills là bản copy** → `pip install -U` + `base install` KHÔNG cập nhật skill trong
  wiki đã init; phải chạy lại `llm-wiki init …` trên từng wiki (idempotent, có prune).
- `init` **không** ghi đè `.llm-wiki.toml` đã tồn tại — chỉ vá thiếu `[wiki]`. Muốn có
  comment/giá trị mới của template thì sửa tay.
- Bản `base_tools/config_file.py` là mirror của `config_file.py`; hai bản này đã từng
  lệch nhau trong im lặng. `doctor` giờ phát hiện, nhưng đó là vá triệu chứng — gốc là
  tách DEFAULTS ra một file mà cả package lẫn base venv cùng đọc.
- Script đo giữ ở scratchpad (`defaults_sweep.py`, `rrf_sweep.py`) — ứng viên để promote
  thành `llm-wiki eval --sweep` (quét `rrf_k`/weights/weights/cutoff mà không cần reindex).
