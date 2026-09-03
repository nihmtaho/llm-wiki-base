# Session — Config Command Code route qua headroom proxy

- **Ngày**: 2026-09-02
- **Nguồn**: yêu cầu của human — model Command Code không xuất hiện trên headroom dashboard
- **Plan**: không có (config trực tiếp)
- **Trạng thái**: hoàn tất + đã verify qua `/stats`. Không commit gì trong repo (chỉ có doc này).

---

## 1. Chuẩn đoán — root cause

1. Headroom proxy **đang chạy tốt** tại `http://127.0.0.1:8787` (`headroom doctor`: 0 failure, 5 warning), đang capture traffic của opencode (`agent_usage` có `opencode` + `claude`).
2. Command Code có 2 BYOK provider trong `~/.commandcode/providers.json` (`opencode-go`, `opencode`) nhưng **connect thẳng** `https://opencode.ai/zen/...` — không qua proxy.
3. Model default lúc đó là `Qwen/Qwen3.8-Flash` — đây là **catalog (gateway) model của Command Code**, traffic đi qua server Command Code, không đi qua máy local → headroom về nguyên tắc không thể capture catalog model.

Kết luận: muốn hiện trên dashboard phải (a) dùng BYOK provider và (b) trỏ `baseURL` của provider đó vào proxy.

## 2. Probe hành vi proxy (trước khi sửa)

- `~/.claude/settings.json` (claude đã route sẵn): `ANTHROPIC_BASE_URL=http://127.0.0.1:8787/w/claude` — headroom có concept workspace `/w/<client>`, nhưng client generic chỉ cần route gốc.
- OpenCode config dùng `baseURL: http://127.0.0.1:8787/v1` — pattern chuẩn cho OpenAI-compatible client.
- `headroom wrap --help`: proxy hỗ trợ **any OpenAI/Anthropic-compatible client** bằng cách tự set base URL; `headroom init`/`wrap` chưa có target `commandcode`.
- Test passthrough `POST /v1/chat/completions` (không có header `x-headroom-*`): proxy tự forward về upstream mặc định `https://opencode.ai/zen/go/v1/chat/completions`, **giữ nguyên Authorization** của client.
- **Gotcha phát hiện**: test bằng `Python-urllib` bị Cloudflare **403** (chặn UA), với curl/UA thường trả 200 cả stream lẫn non-stream → không phải proxy hỏng. Key lưu trong `~/.commandcode/auth.json` dưới `opencode-go.key` (field `key`, không phải `apiKey`).

## 3. Thay đổi đã thực hiện

1. **`~/.commandcode/providers.json`** (backup: `~/.commandcode/providers.json.bak-headroom`):
   - `provider.opencode-go.baseURL`: `https://opencode.ai/zen/go/v1` → `http://127.0.0.1:8787/v1`
   - Không đổi models, headers, các provider khác.
2. **Default model**: `cmd config set model opencode-go/qwen3.8-flash` **THẤT BẠI** (`Unknown model` — lệnh này chỉ accept catalog id, không load BYOK registry). Giải pháp còn lại: chọn qua `/model` trong TUI hoặc cờ `--model` khi chạy. → Human cần tự chọn `/model` → `opencode-go → Qwen3.8 Flash` một lần.
3. **Taste**: ghi nhận workflow + các gotcha trên (BYOK id không set được qua config set; 403 CF là do UA test; dashboard gán agent `openai` cho traffic này).

## 4. Verification

1. Test qua proxy bằng key thật (không in key): `HTTP 200`, trả `completion` hợp lệ — cả non-stream lẫn `stream:true`.
2. `cmd -p "reply with exactly: proxy-ok" --model opencode-go/qwen3.8-flash` → trả lời `proxy-ok`.
3. `GET /stats` sau test: `api_requests` 4 → 8; `agent_usage` có entry `openai` với `models: {qwen3.8-flash: 1, mimo-v2.5: 3, glm-5.3-flash: 1, passthrough:models: 2}` → **model Command Code đã hiện trên dashboard**.
4. `cmd --list-models` còn liệt kê đầy đủ `opencode-go/*` (provider không bị skip sau khi đổi baseURL).

## 5. Files changed

**Modified (1, ngoài repo)**: `~/.commandcode/providers.json` (`opencode-go.baseURL`).
**New (2)**: `~/.commandcode/providers.json.bak-headroom` (backup), doc này.
Repo `llm-wiki-base`: không sửa code; session này phát sinh thêm 1 file dưới `docs/session/`.

## 6. Ghi chú vận hành

- **Điều kiện chạy**: headroom proxy phải sống. Đã có sẵn cơ chế install/deploy chạy thường trực — `headroom install` hoặc `headroom deploy` (doctor hiện proxy đang up qua `.beacon_lock_8787`). Proxy tắt → mọi model `opencode-go/*` fail.
- **Rollback**: restore `providers.json.bak-headroom` (hoặc đổi baseURL về `https://opencode.ai/zen/go/v1`), chọn lại model gateway.
- **Attribution trên dashboard**: traffic Command Code gán nhãn agent `openai` (phân biệt qua wire + UA), không phải `commandcode`. Muốn nhãn riêng thì cần `x-headroom-*` headers — Command Code hỗ trợ `headers` trong providers.json nếu muốn sau này.
- Provider `opencode` (wire `zen/v1`) **chưa** route qua proxy — nếu muốn, thêm entry tương tự trỏ `http://127.0.0.1:8787/v1` kèm header `x-headroom-original-path` cho đúng upstream path.
