# Tier 3 — Roadmap

Nguồn: đánh giá `docs/human-ideas/my-idea/` (OKF v0.2 bundle). Tier 1 + Tier 2 đã áp
(plan `~/.commandcode/plans/llm-wiki-base-tier1-tier2-implementation.md`). **Gói retrieval
(§1–§3 dưới đây) đã áp ngày 2026-09-02** — plan `~/.commandcode/plans/llm-wiki-base-tier3-retrieval.md`,
chi tiết trong `docs/session/session-tier3-retrieval-2026-09-02.md`. Phần còn lại giữ
để làm khi có tín hiệu cần thiết (scale lớn hơn, multi-agent, portability).

## ĐÃ LÀM (2026-09-02) — gói retrieval

### 1. Eval harness → điều kiện bật vector ✅
- `llm-wiki-base eval` (`tools/eval.py`): P@k / R@k / MRR trên `eval/golden.toml` (query vàng, COMMIT).
- `--compare` chạy 3 profile: `tier1-weighted` (baseline) / `rrf-text` / `rrf+vector` + verdict.
- `eval/results.json` (gitignored) append kèm fingerprint config → so sánh theo thời gian.
- `zero_recall_queries` = wiki thiếu tài liệu (việc của ingest), không phải retriever dở.
- Kênh chết **vì lỗi** được in `[ERROR] kênh bị tắt vì lỗi` — tránh số liệu giả.

### 2. Union retrieval + RRF ✅ (rerank vẫn ở skill layer)
- `tools/search.py`: 3 kênh `bm25_page` / `bm25_chunk` / `vector_chunk` → **RRF trên hạng**
  (`rrf_k`, `[retrieval.weights]`). Bỏ full-table-scan page embeddings ở chế độ RRF.
- `fusion = "weighted"` giữ nguyên đường code Tier 1 → rollback 1 dòng + baseline đo được.
- MCP `wiki_search`: gộp cross-wiki bằng RRF trên hạng-per-wiki + khử trùng `(wiki, path)`.
- Kết quả có `matched_by` + `rank` + `snippet` là chunk text → skill dùng để rerank.
- **Còn deferred**: reranker **cross-encoder** trong Python (dep ONNX + model). Hiện rerank
  là bước LLM trong skill (`[retrieval].rerank = "llm"`), theo đúng ý roadmap cũ.

### 3. Chunk-level BM25 (FTS trên chunks) ✅
- Bảng `chunks_fts` trong `.wiki.db` (FTS5 standalone, `page_id`/`path` UNINDEXED).
- `tools/chunking.py` — chunker **dùng chung** với `rag/index.py` → 2 kênh cùng ranh giới.
- Sync trong `search.index_file` → ingest/reindex/watch tự động; `SCHEMA_VERSION` 2→3 ép
  `reindex --full` một lần cho wiki cũ.
- Không chunk: reserved `index.md`/`log.md`, `*.lang.md`, frontmatter, footnote verbatim.

### 3b. Limitation còn lại của gói retrieval (nếu cần, làm sau)
- `wiki/log.md` **vẫn là một page** → vẫn xuất hiện trong `bm25_page` (chỉ phần chunk bị loại).
  Hướng xử lý: `[retrieval] exclude_from_index = ["wiki/log.md"]` (lint + search + rag đọc chung).
- Eval chỉ đo 1 wiki; đường gộp cross-wiki của MCP chưa có metric riêng.
- `pages.embedding` vẫn được ghi nhưng RRF không đọc (chỉ `fusion="weighted"` dùng) →
  candidate để bỏ nếu không ai rollback.

### Gói skills + MCP + config + naming + proposals ✅ (cùng ngày, đợt 2)
Nguồn: `docs/human-ideas/improve/tasks.md`. Chi tiết trong
`docs/session/session-tier3-skills-mcp-config-2026-09-02.md`.
- 13 skill personal/project → **8 skill `llm-wiki-base-*` profile-aware** (chế độ đọc
  `[wiki].profile`); thêm `llm-wiki-base-reindex`; `research` tách khỏi `query` và cài ở
  **root codebase**; `plan` + `mcp` gộp vào `query`/`research`; `translate` giữ + sửa
  bug không bao giờ được cài cho project wiki.
- Phân phối: `.agents/skills/` canonical + symlink cho claude/opencode (port
  `link_skills.sh` — code chết — sang Python, có prune); commandcode không cần link.
- MCP: thêm client `commandcode`, `--mcp-scope user|project`, in rõ path + key + scope.
- Registry: `name` + `id` (UUID), trùng tên khác path → hậu tố `-<uuid8>`; `--no-register`.
- `[wiki].profile`/`lang`, `[models]` (schema), `vector = true` mặc định mới.
- `llm-wiki-base proposals list|show|apply|discard|new` + metadata target trong proposal.
- `llm-wiki-base doctor` + error path thống nhất cho CLI wrapper.

---

## CÒN LẠI

## 4. OKF v0.2 full conformance

- Rename `kind` → `type` (OKF vocabulary), migrate DB + template + skills.
- `index.md` gốc khai `okf_version: "0.2"`; timestamp toàn bộ ISO-8601 có offset (kể cả `updated`).
- Concept ID = đường dẫn bỏ `.md` (đã gần đúng — wikilink vẫn kèm `.md`).
- Bundle root `.wiki/` + `.wiki-index/` gitignored (đổi tên từ `wiki/` + `rag/.rag_index/`).
- **Chi phí**: migration wiki cũ + rewrite lint/db/skills. **Khi nào**: nếu cần portable tooling
  OKF (consumer ngoài) hoặc chuẩn hoá multi-wiki.

## 5. Codebase profile (g3doc layout)

- Cho project wiki mới: layout theo type-first — `requirements/` (intent) vs `modules/` (observation)
  vs `decisions/` (ADR) vs `guides/` thay vì domain-first.
- `x_code_paths` frontmatter cho traceability (review check path còn tồn tại — hiện review đã
  grep code path, x_code_paths chuẩn hoá cách extract).
- **Intent vs Observation rule**: quan sát từ code chỉ thành requirement khi có nguồn xác nhận ý định;
  không rõ → `alerts/`. Cần schema rule + skill ingest phân loại.
- Chỉ áp cho **wiki mới** (init project option `--layout g3doc`); personal wiki giữ domain layout.

## 6. Registry.yml anti-fork cho multi-agent

- Hiện tại: `status: planned` placeholder (đủ cho single maintainer).
- Nâng cấp khi **nhiều agent song song** ghi cùng wiki: `registry.yml` per-wiki reserve Concept ID
  (`planned → active`), claim ID bằng ghi có điều kiện (conditional write) — reasoning ngoài lock.
- Chỉ làm khi thấy fork thực tế xảy ra trong alerts/log.

## 7. Attested Computation (OKF §10) — thay luật copied-state

- Giá trị hay đổi (count, sum, health) KHÔNG copy vào body — tạo concept `type: attested-computation`
  mang cách tính đã duyệt + executor (script chạy trả receipt) + attester (check tất định).
- **Chi phí cao** (executor + receipt format + attester infra). Khi nào: wiki làm nguồn sự thật cho
  dashboard/automation cần verify giá trị live.
- Luật copied-state hiện tại (values trong frontmatter hoặc đọc live) vẫn đủ cho knowledge wiki.

## 8. `[private] dirs` — index nhưng không commit

- Config `[private] dirs = ["scratch"]` — folder trong wiki/ được index (search thấy local) nhưng
  gitignored (không commit).
- Rẻ (~1 giờ): `wiki-gitignore` template + lint check + reindex exclude khỏi... không, vẫn index.
- Làm khi có nhu cầu ghi note riêng tư trong wiki.

## 9. Lint-export wikilink rewrite

- Export mode: rewrite `[[wiki/<domain>/x]]` → `[x](/wiki/<domain>/x.md)` cho consumer không hiểu
  wikilink (GitHub render, static site).
- Command `llm-wiki-base export --out <dir>` — không đổi source.

## 10. Migration tooling wiki cũ

- Script migrate frontmatter page cũ: flat `sources` → dict form, thêm `generated`, `confidence` →
  `verified` mapping (`human-verified` → `verified.by = human`).
- `llm-wiki-base migrate` — dry-run trước, chỉ chạy khi số page cũ đáng kể.

## 11. Headless ingest — `[models]` providers + LLM client thật

- `tasks.md` đòi "config thêm providers cho wiki → ingest không cần mở agent tool".
  **Đã làm một nửa có chủ đích**: section `[models]` (`light`/`heavy`/`provider`/
  `api_key_env`) đã nằm trong config + template, nhưng Python **không đọc** nó và không
  gọi LLM — `llm-wiki-base doctor` nói rõ điều đó.
- Phần còn lại (client OpenAI-compatible/Anthropic để `llm-wiki-base ingest --headless` chạy
  từ cron/watch) **chưa làm**, và không nên làm vội: ingest thật là quy trình nhiều bước
  (plan concept đích, chống fork theo `status: planned`, tôn trọng pins, cập nhật
  index/log, distill-verify) — một lần call API không thay được skill + loop của agent.
  Chi phí thật sẽ là: thêm dependency, quản lý API key, token cost không có gate, và
  phải tự viết lại cơ chế "AI proposes, human decides".
- Nếu làm: bắt đầu từ thứ **đã có cấu trúc rõ** thay vì ingest — `translate` (đầu vào/ra
  xác định, đã có `translate check` để nghiệm thu) rồi mới đến review/consolidate.

---

*Ưu tiên còn lại: **4–5** khi cần portability / codebase profile thật; **6–7** khi multi-agent hoặc
automation trở thành use case thực tế; **8–10** rẻ và không phá gì, làm khi có nhu cầu cụ thể.
Trong nhóm retrieval: reserved pages (`index.md`/`log.md`) đã loại khỏi mọi kênh
index từ fix `search.index_file` + `reindex._collect_files`; `exclude_from_index`
(§3b, do user cấu hình) vẫn là bước tiếp theo nếu wiki của bạn có page dài khác
chiếm kết quả; cross-encoder rerank chỉ khi dùng wiki ngoài AI tool
(script/dashboard) mà vẫn cần chất lượng rerank.*
