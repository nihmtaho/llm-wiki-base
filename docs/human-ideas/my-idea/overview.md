---
type: Overview
title: "LLM-Wiki — vision & thiết kế"
description: "llm-wiki cho codebase, tối giản theo Karpathy, chuẩn hoá bằng OKF v0.2, retrieval hybrid."
status: draft
generated: { by: "claude-code/opus-4.8", at: 2026-09-01T17:14:00+07:00 }
sources:
  - id: karpathy
    resource: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
    title: "Karpathy — LLM Wiki"
  - id: okf
    resource: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
    title: "Open Knowledge Format v0.2 — SPEC"
tags: [meta, design]
x_owner: "human:nihmtaho"
---

# Overview

TL;DR: Knowledge base do LLM viết & bảo trì, con người lái hướng — giữ triết lý tối giản của Karpathy[^karpathy], chuẩn hoá bằng OKF v0.2[^okf], với workflow layer riêng và retrieval hybrid để đáng tin khi lớn dần.

## 1. Mục tiêu
Biến kiến thức project (yêu cầu, quyết định, hành vi code, lịch sử) thành bundle markdown sống cạnh source code, hữu ích qua nhiều phiên agent. Markdown + git là nguồn sự thật; chỉ mục search là derived.

## 2. Kiến trúc một dòng
Karpathy (lõi) → OKF v0.2 (format chuẩn, portable) → workflow layer (profile · pins · reserve · intent/obs · union+hybrid retrieval · governance) → wikilink cho trải nghiệm đọc.

## 3. Quyết định thiết kế chính
- **Hai profile, một lõi**: `codebase` + `personal`, chuyển bằng một dòng.
- **Layout g3doc**: docs-as-code; một concept = một `type` = một mục đích.
- **OKF-conformant thật sự**: đúng tên field OKF; Concept ID = path bỏ `.md`; `index.md`/`log.md` reserved.
- **Wikilink cho concept↔concept** (theo Concept ID); markdown link chỉ cho URL; có lint-export sang markdown link.

## 4. Tầng workflow (ngoài OKF core)
- **Union + hybrid retrieval** — structural (index+wikilink) ∪ hybrid (BM25+vector trên semantic chunk) → rerank; chỉ mục derived, gitignored, rebuild được; fallback tất định khi thiếu model.
- **Pins** — sửa tay lưu dạng *claim*, sống sót qua regenerate; bị nguồn mới hơn phủ định thì đẩy cho người.
- **Reserve Concept ID** — placeholder `planned` chống fork.
- **Intent vs Observation** (codebase) — tách ý định khỏi hành vi quan sát; không bịa yêu cầu.
- **Governance docs-as-code** — đổi cùng PR; duyệt artifact; duyệt = set `verified` → *human-reviewed*.

## 5. OKF chuẩn hoá các ý tưởng tự chế
- Bằng chứng-kèm-citation → footnote keyed theo `sources[].id`.
- Độ tin cậy → trust tier từ `generated` + `verified`.
- Vòng đời → `status` + `stale_after`.
- Copied-state → **Attested Computation** (OKF §10): verify giá trị bằng code tất định.

## 6. Còn để ngỏ
- Concept mẫu (Decision + Attested Computation) để nghiệm thu.
- Eval harness (P@k/R@k/MRR) làm cơ sở bật vector.
- Chốt: dựng profile `codebase` hay `personal` trước.

[^karpathy]: Karpathy — LLM Wiki
[^okf]: Open Knowledge Format v0.2 — SPEC
