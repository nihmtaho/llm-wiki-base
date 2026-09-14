# Session — Setup wizard dạng menu + detect AI client (9 client)

**Ngày**: 2026-09-14
**Nguồn việc**: yêu cầu trực tiếp — *"implement re design cli khi setup với cli lựa chọn thay vì bắt người dùng nhập. đối với mcp thì detect trong máy và cho phép người dùng chọn cái mong muốn"*. Đây là dòng còn nợ từ spec `docs/superpowers/specs/2026-09-03-cli-redesign-design.md` §5: *"MCP clients (multi-select, **pre-checked to installed clients**)"* — spec đã duyệt từ 2026-09-03 nhưng chưa từng được code.
**Plan**: `~/.commandcode/plans/cli-setup-select-mcp-detect.md` (qua plan mode, đã duyệt).
**Branch**: `feat/setup-select-clients` · **Trạng thái**: đã implement, đã verify trên máy thật, **đã commit 9 commit**, chưa push.

---

## 1. Quyết định chính

4 ngã rẽ được hỏi trước khi code. Hai trong số tôi chọn phương án khác khuyến nghị của chính mình vì người dùng phản đối:

| ngã rẽ | quyết định | lý do / cái bị từ chối |
|---|---|---|
| Widget chọn | **questionary** (arrow-key TUI) | Tôi khuyến nghị menu số tự viết trên rich (không thêm dep, giữ được piped stdin). Người dùng chọn TUI → chấp nhận `questionary` + `prompt-toolkit`. Hệ quả: mọi câu hỏi đi qua façade `_prompt.py` thay vì gọi thẳng, vì `CliRunner(input=...)` và CI không có TTY |
| Bộ client | **9** — claude, opencode, commandcode, zed, cursor, copilot, codex, pi, hermes | Tôi khuyến nghị giữ 4 client đã có đường ghi config. Người dùng mở rộng và tự cung cấp docs từng client. Đường dẫn + key + format của 5 client mới đều **lấy từ docs chính chủ**, không đoán |
| Không detect được gì | bỏ trống hết + vẫn liệt kê đủ 9 kèm **lý do** | Không suy đoán hộ. Chọn sai client còn tệ hơn không chọn |
| Phạm vi menu | wiki type + clients + skills target + confirm → menu; name/root/subdir/lang → text | Menu chỉ có nghĩa với quyết định dạng danh sách; bắt chọn đường dẫn bằng menu thì vô ích |
| PyYAML | **KHÔNG thêm** | Venv đã có PyYAML (transitive của `trafilatura`) nhưng dùng nó để round-trip `~/.hermes/config.yaml` = nướng sạch comment của người dùng. Chỉ dùng làm **oracle** khi verify |
| TOML round-trip | **KHÔNG** — cùng lý do, dù `tomli_w` đã là dep sẵn | Ghi bằng managed block, parse lại để **chặn** trước khi ghi file hỏng |

---

## 2. Implement theo mảng

### 2.1 `_prompt.py` — façade TTY-aware (mới, 224 dòng)

`select` / `checkbox` / `text` / `confirm` / `split_csv`. Mỗi hàm: có TTY + questionary thì vẽ menu, không thì **đúng câu hỏi rich như trước đây** — nên `--yes`, pipe và CI không đổi hành vi. Lý do fallback chỉ in khi `--debug` để không nhiễm assertion của test. Switch khẩn: `LLM_WIKI_BASE_NO_MENU`.

Hai bug tự mắc lúc viết test (không phải bug production nhưng là bài học):
- `monkeypatch` `input()` bằng hằng số `"\n"` → rich lặp vô hạn vì nó chỉ nhận default khi value **rỗng sau strip**, không phải `"\n"`. Test giờ feed `""`.
- Hint dạng `"[space to toggle]"` bị rich **ăn mất như markup** → chuyển sang `·`. Cùng cơ chế `_plain()` strip markup trước khi đưa questionary (questionary không hiểu `[red]…`).

### 2.2 `clients.py` — engine detect (mới, 155 dòng)

Ba bằng chứng, **một là đủ**: `shutil.which(binary)` → config dir user-scope → app bundle macOS. `ClientState(key, label, detected, evidence, target, scope)`; `choices()` sinh nhãn menu `[✓]/[?]` kèm evidence, `as_rows()` cho doctor, `client_flags()` cho dòng copy-paste.

Toàn bộ path `~`-relative **expand lúc gọi** (bảng `CLIENT_PATHS` lưu chuỗi, không lưu `Path`) — `Path.home()` đóng băng lúc import sẽ làm `monkeypatch.setenv("HOME", …)` vô hiệu. `APPS_ROOT` là module constant cũng vì lý do đó.

Kết quả đo trên máy này: detect `claude, opencode, zed, commandcode, pi, copilot`; **không** `cursor, codex, hermes` — đúng kỳ vọng.

### 2.3 `config.py` — bảng 9 client

Mỗi entry giờ mang `label / mcp_key / format / detect{binaries,paths,apps} / project_mcp` (+ `allow_user_scope`). `MCP_KEYS` và `supported_clients()` **dẫn xuất** từ bảng → hết cảnh help text hard-code 4 tên. Zed lấy lại project scope qua `.zed/settings.json` (xác nhận từ issue zed-industries/zed#62829) nên không còn là client bị skip.

Sự khác biệt thật của từng client được ghi thành comment trong bảng: cursor bắt buộc `type: "stdio"` và **không nhận `cwd`**; copilot dùng key `servers` (không phải `mcpServers`) và `mcp_file: None` để mọi ý định ghi user-scope phải raise; hermes `project_mcp: None` + `allow_user_scope: True`.

### 2.4 `_blocks.py` — sửa TOML/YAML không mất comment (mới, 341 dòng)

```
# BEGIN llm-wiki-base (managed by `llm-wiki-base setup`; server=<name>)
[mcp_servers.<name>]  command = "llm-wiki-base"  args = ["serve", "--mcp"]
# END llm-wiki-base
```

`upsert` = cắt block theo **từng server name** rồi chèn lại (idempotent, hai server khác tên → hai block). Với YAML: nếu file đã có `mcp_servers:` thì chèn **vào trong** mapping đó, kế child cuối, và **theo đúng indent của file** (4-space nếu chủ file dùng 4-space) — một top-level key thứ hai là duplicate. Không có mapping nào thì ta tự viết header. `validate()` parse lại kết quả (TOML bằng `tomllib`, YAML bằng kiểm tra duplicate-key + tab vì cố ý không có parser) → **từ chối ghi** thay vì ghi file hỏng. `drop()` gỡ được cả entry viết tay.

### 2.5 `installer.py` — writer theo format

`install_mcp_config` tách thành `_install_json` (round-trip như cũ) và `_install_block` (TOML/YAML). `install_centralized_mcp` nới guard: `scope="user"` chỉ hợp lệ khi client có cờ, vẫn raise cho 8 client kia — bất biến "chỉ ghi project scope" giờ được enforce ở tầng hàm và **có tên của client vi phạm** trong message. JSONC có comment → message riêng nói rõ vì sao không ghi đè (thay vì "not valid JSON" gây hiểu nhầm).

### 2.6 `cli.py` — wizard + khả năng quan sát

- Bare `setup`: `select` wiki type → `text` name/root → **`checkbox` clients pre-checked theo detect** → summary → `confirm`.
- `--interactive` khôi phục lang/skills/MCP; `--no-mcp` không bao giờ hỏi.
- `-c` mặc định `None` = "tự detect"; truyền `-c` = "đúng bấy nhiêu, đừng đoán".
- Dòng `MCP:` trong summary **nhóm theo file đích**: `.mcp.json ← claude, commandcode, pi · .codex/config.toml ← codex · GLOBAL ~/.hermes/config.yaml ← hermes`. Write global hiện chữ GLOBAL ngay trên màn hình xác nhận.
- Lệnh mới **`setup clients`** + bảng AI clients trong **`setup doctor`** (Client | Installed | Evidence | Writes) — trả lời "sao menu không pre-check cái của tôi" mà không phải đọc code.
- Xoá `--here`: flag khai báo nhưng chưa từng được đọc trong body.
- Ở chế độ không-TTY, checkbox in danh sách đánh số + lý do `not detected`, và chấp nhận trả lời bằng **số** (`1,8`) cũng như tên.

### 2.7 `init_personal.py` / `init_project.py` — hai chỗ lệch đã sửa

Personal trước đây **âm thầm** suy ra `["claude"]` khi danh sách rỗng (project thì bỏ qua), và client lạ chỉ in warning giữa chừng (project thì exit 1). Nay cả hai: validate **trước khi ghi đầu tiên**, và "không client nào" là một dòng in rõ ràng chứ không im lặng. Hermes được cài thật: loop chọn `scope="user"` cho client có cờ.

---

## 3. Kiểm chứng

| # | việc | kết quả |
|---|---|---|
| 1 | `pytest tests/ -q` | **155 passed** (đầu phiên: 85) — thêm 70 test |
| 2 | `ruff check src tests` | All checks passed |
| 3 | `mypy` trên 7 module chạm vào | Success: no issues |
| 4 | Menu questionary **có thật sự render**? | chạy qua `pty.spawn` + pipe phím: vẽ `? Wiki type (Use arrow keys)`, checkbox 9 dòng với `[✓]`/`[?]` + evidence, `done (6 selections)`, trả `n` ở confirm → wiki **không** bị tạo |
| 5 | Detect trên máy thật | 6 có / 3 không, đúng dự đoán (`setup clients`) |
| 6 | Ghi đủ 9 client vào HOME giả | exit 0; 8 file (claude+commandcode+pi dùng chung `.mcp.json`) |
| 7 | File ra **parse được bằng parser thật** | `tomllib` OK cho codex; `yaml.safe_load` OK cho hermes (`{'mcp_servers': {'llm-wiki-base-mcp': {command, args}}}`); 5 file JSON OK hết |
| 8 | `uninstall --dry-run` nhìn thấy đủ? | liệt kê 7 file, gồm `.codex/config.toml` và `~/.hermes/config.yaml` |
| 9 | Gỡ thật: phần của chủ file còn nguyên? | codex: block của ta biến mất, `[mcp_servers.context7]` + `# mine` **còn nguyên**; hermes: `profile:`/`model:` còn, entry của ta sạch; `.mcp.json` (chỉ có ta) bị xoá file |
| 10 | Idempotency | chạy `setup` 2 lần → 1 block, 1 table; `cwd` đổi thì ghi đè đúng chỗ |
| 11 | Comment của user được giữ? | `assert 'comment cua toi' in config.toml` → PASS (test tự động hoá ý này) |

Reproduce:

```bash
PYTHONPATH=src python -m pytest tests/ -q
ruff check src tests
mypy src/llm_wiki_base/cli.py src/llm_wiki_base/registry.py \
     src/llm_wiki_base/_prompt.py src/llm_wiki_base/_blocks.py \
     src/llm_wiki_base/installer.py src/llm_wiki_base/clients.py src/llm_wiki_base/config.py

D=$(mktemp -d); mkdir -p "$D/home" "$D/base" "$D/wiki"; cd "$D/wiki"
export HOME="$D/home" LLM_WIKI_BASE_DIR="$D/base" PYTHONPATH=<repo>/src
llm-wiki-base setup clients
llm-wiki-base setup personal -n demo -c claude -c codex -c hermes -c zed --no-skills -y
llm-wiki-base uninstall --dry-run --path "$D/wiki"
```

---

## 4. Files

**Mới (7)**: `src/llm_wiki_base/_prompt.py`, `src/llm_wiki_base/clients.py`, `src/llm_wiki_base/_blocks.py`, `tests/test_prompt_fallback.py`, `tests/test_blocks.py`, `tests/test_installer_formats.py`, `tests/test_clients_detect.py`

**Sửa (13)**: `pyproject.toml` (+`questionary>=1.10`), `src/llm_wiki_base/config.py`, `installer.py`, `cli.py`, `init_personal.py`, `init_project.py`, `_ui.py` (+`is_no_color()`), `tests/conftest.py` (+fixture `machine`), `tests/test_wizard.py`, `docs/mcp.md`, `docs/cli.md`, `docs/init.md`, `README.md`

Tổng trên branch `feat/setup-select-clients` (`9bb5f2a..HEAD`, 1 commit squashed):
**21 file, ~+2330/−173** — con số insertions lệch vài dòng theo chính file này,
nên làm tròn; `git diff --stat 9bb5f2a..HEAD` là nguồn đúng.

---

## 5. Ghi chú vận hành

**Commit** — branch `feat/setup-select-clients` cuối cùng mang **1 commit squashed**
(`feat(cli): choose setup answers from menus and detected clients`), validate qua
guard của skill `git-commit`, không trailer AI, không commit trên `main`.

11 commit phát triển trong quá trình làm (đã squash, giữ lại đây để truy vết nếu cần
`git reflog`; commit cũ là `f667103`):

```
04134e6 feat(cli): add TTY-aware prompt facade for setup menus
37bbbdc feat(cli): probe installed AI clients instead of assuming them
976beb0 fix(cli): keep defaults and hints in the non-TTY prompt path
b85c31b feat(config): add pi, cursor, copilot, codex, hermes client entries
2488b4e feat(installer): edit TOML and YAML configs as managed blocks
4ff8347 fix(installer): stop rich from eating the install location line
ac5c378 fix(init): never guess claude as the MCP client, and fail before writing
633e370 feat(cli): pick setup answers from menus and detected clients
38dccbe fix(cli): leave no blank-line pile where a managed block was
b7160c3 docs: cover the 9 clients, detection, and the two non-wiki writes
f667103 docs(session): record the setup menu + client detection work
```

Squash bằng `git reset --soft 9bb5f2a` + một commit mới; kiểm bằng
`git rev-parse HEAD^{tree}` trước/sau — **tree byte-identical**, nên không có nội
dung nào thay đổi ngoài lịch sử.

**Va chạm phiên song song**: giữa phiên phát hiện `clients.py` + `tests/test_clients_detect.py` **đã tồn tại trong HEAD** nhưng bị xoá khỏi worktree, và `config.py` bị lùi về bản 4 client — một phiên agent khác đang làm cùng plan trên cùng repo (2 commit `04134e6`, `37bbbdc` không phải do phiên này chạy). Xử lý: backup 3 file đang mở sang scratchpad → `git checkout --` khôi phục từ HEAD → giữ lại phần `_prompt.py`/test của phiên này (mới hơn: 2 bug fix) → 101 test xanh rồi mới đi tiếp. **Không có work nào bị ghi đè.** Bài học: trước khi sửa tiếp một file đã "unexpectedly modified", phải `git status` + `git log` để biết HEAD đã đi tới đâu.

**Bug production tìm ra nhờ verify, không phải nhờ đọc code**: `McpInstall.describe()` đặt giải thích *nơi ghi* trong `[...]` → khớp regex markup của rich → cả cụm **"project: …" / "GLOBAL: …" bị ẩn hoàn toàn** từ trước tới nay. Nếu không chạy thật để đọc output thì không bao giờ thấy, vì unit test chỉ assert chuỗi trả về.

**Không làm được qua CLI**: phần menu arrow-key chỉ chạy được có TTY. Không có cách nào để tôi tương tác thật, nên verify bằng `pty.spawn` + gửi phím — đủ chứng minh questionary render và luồng đi tới `confirm`, nhưng **không** thay được cảm nhận sử dụng thật. Người dùng nên tự chạy `llm-wiki-base setup` một lần trong terminal.

**Còn nợ / follow-up**:
1. Push + mở PR vào `develop` (branch đang 9 commit ahead, chưa push).
2. `llm-wiki-base upgrade --dry-run` trên một wiki đã có sẵn, coi 9 client có làm installer/upgrade hiểu nhầm file cũ không — checkpoint đã ghi trong plan, **chưa chạy**.
3. `src/llm_wiki_base/templates/mcp/` mới có 3 sample (claude, opencode, zed). Message từ chối JSONC trỏ vào `templates/mcp/<client>.mcp.sample.json` — hiện không trỏ nhầm (chỉ opencode/zed đi nhánh đó) nhưng thêm sample cho cursor/copilot/codex/pi/hermes vẫn nên làm.
4. Codex: `.codex/config.toml` project-scope chỉ được đọc khi project là **trusted** → đã ghi trong `docs/mcp.md`; cân nhắc nhắc lại ngay sau khi setup xong.
5. Một `.mcp.json` rỗng (`{"mcpServers": {}}`, 23 bytes) tồn tại ở **repo này** và của một session khác đã tạo; không phải sản phẩm của phiên này nên tôi để nguyên, chưa track.
