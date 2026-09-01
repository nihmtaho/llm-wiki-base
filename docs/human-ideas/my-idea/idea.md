---
type: Schema
title: "LLM-Wiki — OKF-conformant bundle contract"
description: "Hợp đồng cho một knowledge bundle theo OKF v0.2, do LLM duy trì, con người lái hướng."
status: active
---

# SCHEMA.md — LLM-Wiki (OKF v0.2 conformant)

Bundle này tuân thủ Open Knowledge Format v0.2. Agent đọc file này trước mọi thao tác.
OKF là tầng FORMAT (portable); workflow (profile, pins, reserve, intent/obs, retrieval) là EXTENSION
trên OKF core — consumer OKF khác bỏ qua an toàn.

---

## 0. Profile  (extension)
```yaml
profile: codebase        # codebase | personal
lang: vi
```
Cấu hình chi tiết ở `wiki.config.toml` (xem file example). Lõi & thao tác giống nhau ở cả hai profile.

---

## 1. Triết lý
- Bundle là plain markdown trong git; **git là nguồn sự thật**. Chỉ mục search là derived, tái tạo được, không commit.
- LLM viết & bảo trì concept; con người curate nguồn, quyết định, phán xử mâu thuẫn.
- Docs-as-code: mỗi concept có owner, đổi cùng PR với code, review như code.
- Phân lao động: FACT = AI viết tự động · JUDGMENT = luôn có con người xác nhận (qua `verified`, §6).

---

## 2. Ba lớp (Karpathy) ↔ OKF
1. **Raw / sources** — `raw/` (và `references/`): nguồn bất biến, chỉ đọc. Là `sources[].resource`.
2. **Wiki / concepts** — file `.md` concept do LLM sinh, TÁI SINH TỪ RAW. Không tái sinh concept từ concept.
3. **Schema** — file này.

---

## 3. Điều kiện conformant (OKF floor)
- Mọi `.md` không phải `index.md`/`log.md` là **concept**, PHẢI có frontmatter YAML hợp lệ + `type` không rỗng.
- `index.md`/`log.md` là tên reserved, viết thường; chỉ `index.md` gốc khai `okf_version`.
- **Concept ID = đường dẫn file bỏ `.md`**.
- Consumer chấp nhận `type` lạ, giữ nguyên key lạ. → extension an toàn.
- Timestamp: ISO-8601 có offset UTC.
- Actor: agent `<producer>/<version>` · người `human:<id>` · tiến trình `process:<id>`.

---

## 4. Cấu trúc bundle
```
.wiki/                    # bundle root (source of truth)
  index.md                # reserved: landing/định tuyến; khai okf_version ở gốc
  log.md                  # reserved: lịch sử theo thời gian
  SCHEMA.md               # concept type: Schema
  overview.md             # concept type: Overview
  wiki.config.toml        # cấu hình (profile, retrieval, models, categories)
  registry.yml            # auxiliary (.yml): reserve Concept ID (§12)
  pins.yml                # auxiliary: human corrections (§11)
  raw/                    # nguồn bất biến, chỉ đọc
  references/             # (tùy chọn) nguồn nội bộ được sources[] trỏ tới
.wiki-index/              # DERIVED, gitignored: BM25/vector/chunks — KHÔNG commit
```

### profile: codebase — thêm
```
  requirements/   # type: Requirement — ý định sản phẩm
  decisions/      # type: Decision (ADR) — quyết định & đánh đổi
  modules/        # type: Reference|Concept — kiến trúc & hành vi quan sát của code
  guides/         # type: Playbook|Tutorial — how-to, onboarding
  alerts/         # type: Reference — mâu thuẫn, open questions, gaps
```
sources: transcript session, PR, meeting note, doc yêu cầu.

### profile: personal — thêm
```
  entities/  # type: Entity     concepts/ # type: Concept
  sources/   # type: Source     analyses/ # type: Analysis
```
sources: bài viết, podcast note, nhật ký, sách, video.

---

## 5. Concept document
```yaml
---
type: Decision                       # REQUIRED (OKF, open vocabulary)
title: "..."
description: "Một câu tóm tắt."
resource: null                       # URI asset gốc nếu có
tags: [db, infra]

generated: { by: "claude-code/opus-4.8", at: 2026-09-01T09:00:00+07:00 }
verified:  { by: "human:nihmtaho",       at: 2026-09-01T10:00:00+07:00 }  # vắng = unverified
status: active                       # draft | active | deprecated | superseded
stale_after: 2027-01-01T00:00:00+07:00

sources:
  - id: s1
    resource: raw/2026-08-30-session.md
    title: "Session bàn về DB"
    author: "human:nihmtaho"
    last_modified: 2026-08-30T00:00:00+07:00

# --- EXTENSIONS (ngoài OKF core) ---
x_code_paths: [src/db/*]             # traceability (codebase)
x_supersedes: null                   # Concept ID bị thay thế
x_owner: "human:nihmtaho"
---
```
Body: dòng đầu TL;DR; markdown có cấu trúc; heading quy ước `# Schema`, `# Examples`, `# Computation`.
Attribution per-claim = footnote keyed theo `sources[].id`, kèm trích verbatim bằng chứng:
```
Chọn Postgres cho production.[^s1]
Mở rộng [[decisions/postgres|bản ADR]] và ảnh hưởng [[modules/billing]].

[^s1]: Session bàn về DB
    > [human:nihmtaho] "prod phải là Postgres, SQLite chỉ để test local"
```

---

## 5b. Liên kết  (extension — lệch có chủ đích khỏi OKF)
- Concept↔concept: **wikilink theo Concept ID** — `[[modules/billing]]`, `[[decisions/postgres|Postgres]]`.
- Markdown link `[text](url)` CHỈ cho URL ngoài.
- Đây là điểm duy nhất lệch OKF; bù bằng lint-export rewrite `[[modules/billing]]` → `[billing](/modules/billing.md)`.
- Đổi tên file = đổi Concept ID → rewrite mọi wikilink (lint bắt gãy).

---

## 6. Trust, lifecycle, provenance (OKF §5)
- **generated** (`by`,`at`) — cách nội dung hiện tại được sinh.
- **verified** (`by`,`at`) — ai xác nhận. Trust tier: vắng = *unverified* · agent = *machine-confirmed* · `human:*` = *human-reviewed*. JUDGMENT chỉ canonical khi *human-reviewed*.
- **status / stale_after** — vòng đời. Lỗi thời: `deprecated`|`superseded` + `x_supersedes`; không xóa, để con trỏ.
- **sources + signals** (`author`,`usage_count`,`last_modified`) — provenance. Vắng `verified` mang nghĩa, không bị loại.
- **Provenance before canon**: `raw/` là bằng chứng; canonical chỉ sau khi tích hợp có ý thức.

---

## 7. Attested Computation (OKF §10) — thay luật copied-state
Giá trị hay đổi KHÔNG copy vào body. Tạo concept `type: Attested Computation` mang cách tính đã duyệt +
executor (chạy trả receipt) + attester (code tất định no-LLM kiểm receipt → verdict). Consumer verify bằng chạy lại.
Giá trị KHÔNG đổi (path tuyệt đối, hostname, branch) viết literal. Narrative lịch sử để literal.

---

## 8. Quy ước nội dung  (extension)
- **Intent vs Observation (codebase):** ý định ở `requirements/`; quan sát code ở `modules/`. Quan sát chỉ thành yêu cầu khi có nguồn xác nhận ý định. Không rõ → open question vào `alerts/`, không bịa.
- **Single source per fact.** Định nghĩa một lần; nơi khác chỉ link (wikilink) hoặc `sources`.
- **Một concept = một `type` = một mục đích** (g3doc). Không trộn loại.

---

## 9. Truy xuất  (extension) — hybrid, index là derived
- **Nguồn sự thật là markdown.** BM25/vector/chunk là **derived state** ở `.wiki-index/`, gitignored, rebuild bất cứ lúc nào.
- **Union retrieval (hai chân + rerank):**
  - structural: `index.md` + đồ thị wikilink.
  - hybrid: `BM25(top_k)` ∪ `vector(top_k)` trên **semantic chunk** của body.
  - lấy hợp → khử trùng → rerank (cross-encoder|LLM) → `top_n_final`.
- **Semantic chunking:** cắt theo ranh giới section (~`chunk_tokens`), giữ heading làm ngữ cảnh. **Loại khỏi index:** footnote/bằng chứng verbatim + frontmatter thô (không tốn recall budget).
- **Câu trả lời trích dẫn concept/`sources[].id`, KHÔNG trích thẳng chunk thô** — chunk chỉ để *tìm* concept; giữ nguyên trust tier.
- **Fallback tất định:** thiếu embeddings/rerank → chạy structural + BM25. "Không model" ≠ "hỏng".
- **Ngưỡng:** dưới ~100k token, index+BM25 đủ; bật vector khi vượt mức hoặc khi eval cho thấy recall tụt.
- Cấu hình ở `[retrieval]` trong `wiki.config.toml`. Bật vector chỉ sau khi eval (P@k/R@k/MRR) trên bộ query vàng.

---

## 10. Thao tác
- **ingest** — thả nguồn vào `raw/` → đọc, bàn takeaway, RESERVE Concept ID (§12), phân loại intent/obs, viết concept theo §5, tôn trọng pins (§11), cập nhật `index.md` + registry + `log.md`, **rồi reindex tăng dần các concept vừa đổi vào `.wiki-index/`**.
- **query** — `index.md` → union retrieval (§9) → trả lời có attribution; câu trả lời giá trị lâu dài file lại thành concept.
- **consolidate** — gộp `log.md` vào concept canonical; additive, tái grounding từ raw; distill-verify (citation không co lại); reindex phần đổi.
- **index / reindex** — dựng/làm mới `.wiki-index/` từ markdown (tăng dần theo content-hash; full rebuild khi cần). Không commit.
- **lint** (tất định) — frontmatter/`type`, reserved, wikilink gãy, sai dạng link, trùng Concept ID, `index.md` cũ, **`.wiki-index/` lệch so với markdown**, thiếu `x_owner`, trộn type, timestamp sai, footnote↔`sources` khớp, reservation cũ, pin orphan. Sửa an toàn tự động.
- **review** (sinh sinh, có nhịp) — mâu thuẫn, claim quá `stale_after`, khái niệm thiếu, traceability, intent-obs drift, trust gap, pin conflict → gaps vào `alerts/`; tự đóng khi vắng hai lần.

---

## 11. Human corrections — pins.yml  (extension)
```yaml
- concept: modules/billing
  kind: correction            # correction | addition | deletion
  claim: "Ngưỡng áp theo từng shipment, không theo tài khoản seller"
  anchor: "## Registration thresholds"
  provenance: "human:nihmtaho"
  status: active
```
Sau regenerate: còn đúng → giữ; bị nguồn mới hơn phủ định → đẩy cho người (không revert âm thầm); section mất → orphan. Nạp nguồn mới không xóa nội dung con người thêm.

---

## 12. Chống fork — registry.yml  (extension)
```yaml
- concept: requirements/eori-number
  type: Requirement
  status: planned             # planned -> active khi concept được ghi
```
Session sau thấy `planned` → chọn update, không create. Reasoning ngoài lock; claim ID bằng ghi có điều kiện.

---

## 13. Governance (docs-as-code)
- Concept đổi cùng PR với code; PR review là chốt duyệt concept do AI viết.
- **Duyệt artifact, không duyệt kế hoạch.** Tầng canonical: pre-generate nháp, người duyệt diff. Duyệt = set `verified` → *human-reviewed*.

---
*Drafted with Dia*
