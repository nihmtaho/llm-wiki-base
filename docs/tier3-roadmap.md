# Tier 3 — Roadmap (deferred)

Nguồn: đánh giá `docs/human-ideas/my-idea/` (OKF v0.2 bundle) — các ý đã áp Tier 1 + Tier 2 (xem plan
`~/.commandcode/plans/llm-wiki-tier1-tier2-implementation.md`). Đây là phần **chưa áp**, lưu để làm sau
khi có tín hiệu cần thiết (scale lớn hơn, multi-agent, eval harness). Thứ tự theo giá trị/chi phí.

## 1. Eval harness → điều kiện bật vector (ưu tiên cao khi wiki lớn)

- Bộ query vàng (20–50 query thật từ usage) + metric **P@k / R@k / MRR**.
- Script đo: chạy `hybrid_search` BM25-only vs BM25+vector, so sánh trên query vàng.
- **Điều kiện bật `vector = true`**: eval cho thấy recall tụt khi BM25-only. Trước đó giữ mặc định tắt.
- Lưu kết quả eval vào `wiki/.eval/` (gitignored) để so sánh theo thời gian.

## 2. Union retrieval + RRF + rerank

- Hiện tại: weighted sum BM25 + cosine (page-level) — không rank-fusion.
- Nâng cấp: **union** BM25(top_k) ∪ vector(top_k) → khử trùng → **RRF** (reciprocal rank fusion)
  thay weighted sum (ổn định hơn vì BM25 score scale khác cosine) → `top_n_final`.
- **Rerank**: cross-encoder (ONNX, thêm dep) hoặc LLM của tool đang chạy (giống cách translate).
  Rerank ở skill layer (query/research skill chọn lại top_n_final từ kết quả search) trước khi
  thêm vào code — tránh dep nặng.
- Config sẵn có: `[retrieval] mode`, `top_k_bm25`, `top_k_vector`, `top_n_final`.

## 3. Chunk-level BM25 (FTS trên chunks)

- Hiện tại: BM25 page-level (FTS5 trên `pages`), chunk chỉ dùng cho vector.
- Nâng cấp: bảng `chunks_fts` (FTS5 trên chunk text) → BM25 chunk-level, fuse với vector chunk-level.
- Lợi ích khi wiki dài (page nghìn dòng): recall chính xác hơn theo section.
- Đi kèm: `reindex` incremental đã sẵn sàng (chunks có file-hash).

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
- Command `llm-wiki export --out <dir>` — không đổi source.

## 10. Migration tooling wiki cũ

- Script migrate frontmatter page cũ: flat `sources` → dict form, thêm `generated`, `confidence` →
  `verified` mapping (`human-verified` → `verified.by = human`).
- `llm-wiki migrate` — dry-run trước, chỉ chạy khi số page cũ đáng kể.

---

*Ưu tiên đề xuất: 1 (eval) → 2 (RRF+rerank) → 3 (chunk BM25) khi wiki vượt ~100k token; 4–5 khi cần
portability/codebase profile thật; 6–7 khi multi-agent/automation trở thành use case thực tế.*
