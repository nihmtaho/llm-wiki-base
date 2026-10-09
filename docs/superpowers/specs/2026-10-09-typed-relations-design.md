# Typed Relations + Claims + Language Packs — Design Spec

Date: 2026-10-09
Status: approved (design), pending implementation plan
Target: llm-wiki-base core + opt-in `japanese` language pack
Driver: nihmtaho-japanese-wiki ingest currently only *files* raw sources into pages linked by untyped wikilinks; it does not build real knowledge (typed relations, cross-source synthesis, provenance-granular claims).

## 1. Goals

1. **Typed relations**: pages declare machine-checkable relations (`contrast-with`, `example-of`, `covered-in`, …) in frontmatter and inline; core extracts them into a deterministic `links` table in SQLite.
2. **Atomic claims with provenance**: a `## Claims` section convention where each bullet is one atom with ≥1 footnote to `sources:`.
3. **Cross-source synthesis**: ingest revisits and *updates* existing pages when a new raw touches the same knowledge, instead of only adding pages.
4. **Language pack opt-in**: language-specific kinds (`grammar-point/`, `vocab/`), relation vocabulary, and slug rules ship as a per-wiki config opt-in (`[langpack]` in `.llm-wiki-base.toml`). Wikis without a pack are 100% unaffected.
5. **Documentation**: full user-facing guides (`docs/relations.md`, `docs/langpacks.md`, migration guide).

## 2. Non-goals (scope guard)

- No retrieval/RRF changes (graph-expand in query skill is roadmap only).
- No translation changes.
- No backfill of existing wikis; old pages remain valid and migrate gradually via consolidate/review.
- No LLM in the extraction path — extraction/sync is deterministic Python, same contract as chunking.

## 3. Architecture decisions (approved)

| Decision | Choice |
|---|---|
| Mechanism | Approach A: frontmatter `relations:` as primary source + DB-derived graph |
| Inline syntax | Supplementary: `[[path\|rel:<type>]]` and `[[path\|rel:<type>\|note]]` (reserved `rel:` prefix in wikilink alias) |
| Default edges | Plain `[[path]]` / `[[path\|alias]]` produce edge `rel: related` (preserves orphan detection and graph continuity) |
| Storage | New `links` table; DB schema of `pages` untouched |
| Language structure | Core chung + language pack opt-in (`[langpack]` section) |
| Migration | Gradual — no backfill pass |

## 4. Data model

### 4.1 `links` table (`db.py`)

```sql
CREATE TABLE IF NOT EXISTS links (
  src    TEXT NOT NULL,   -- source page path, e.g. wiki/languages/grammar-point/ba.md
  rel    TEXT NOT NULL,   -- relation type, e.g. contrast-with
  dst    TEXT NOT NULL,   -- target path, optionally with #anchor
  note   TEXT,            -- AI-authored context (optional)
  src_footnote TEXT,      -- footnote id, e.g. s1 (optional)
  origin TEXT NOT NULL,   -- 'frontmatter' | 'inline' | 'wikilink'  (debug drift)
  PRIMARY KEY (src, rel, dst)
)
```

### 4.2 `tools/graph.py` (new module)

- `extract_links(page_text) -> list[Link]` — pure function parsing frontmatter `relations:` + inline typed links + default wikilink edges. No I/O.
- `sync_links(db, page_path, page_text)` — upsert edges of one file, GC edges of that file no longer present. Called from `ingest.py` per-file and from `reindex` for full reconcile; `reindex --full` rebuilds the table from scratch.
- Parse failures → warning + skip (same posture as `ingest.py` today). Missing `dst` → tolerated at parse time; lint raises `broken-relation-target`.

## 5. Page contract

### 5.1 Frontmatter `relations:` (primary)

```yaml
relations:
  - rel: contrast-with
    target: wiki/languages/grammar-point/ba.md
    note: "〜たら nhấn hậu quả tình cờ"
    source: s1        # optional — footnote id in sources:
```

### 5.2 Inline typed wikilinks (supplementary)

```
[[wiki/languages/grammar-point/ba.md|rel:contrast-with]]
[[wiki/languages/grammar-point/ba.md|rel:example-of|Ví dụ của 〜たら]]
```

- `rel:` is a **reserved alias prefix**. Lint rule `inline-rel-vs-alias` warns on conflicting definitions (same dst, different rel).
- Duplicate (src, dst, rel) across both forms → deduped by primary key; frontmatter `note` wins on conflict.

### 5.3 `## Claims` section (atomic facts)

```markdown
## Claims

- 〜たら dùng để chỉ việc "sau khi X xảy thì Y" với sắc thái tình cờ, không chủ đích.[^s1]
- 〜たら có thể dùng cho điều kiện tương lai "nếu X thì Y", thay thế 〜ば trong nói.[^s1]
- Shinkanzen N3 bài 6 xếp 〜たら vào nhóm điều kiện, không nhóm "sau khi".[^s2]
```

Rules (added to `_schema.md`):

- One bullet = one claim atom = exactly one sentence, ≥1 footnote `[^id]` → `sources:` dict. No multi-idea bullets.
- Footnotes keep current verbatim-quote semantics; `lint footnote-sources-match` unchanged. Claims *organize* the citation system, not replace it.
- Claim-vs-claim links use inline anchors:
  `- 〜ば nhấn điều kiện logic.[^s2] [[wiki/languages/grammar-point/ba.md#claims|rel:contradicts]]`
  The parser scans the target page's `## Claims` section; edge `note` carries the source claim text.
- Cross-source ingestion: a new raw that *agrees* with an existing claim → add a new footnote to that claim (more provenance). A new raw that *contradicts* → never edit the old claim; add `rel: contradicts` + open `wiki/alerts/` (contradictions stay human-resolved).
- Claims are prose content, not a new page kind.

## 6. Language pack (`[langpack]`)

Per-wiki opt-in in `.llm-wiki-base.toml`:

```toml
[langpack]
enabled = true
pack = "japanese"           # resolved from templates/langpacks/<pack>/
```

Pack layout in core:

```
templates/langpacks/japanese/
├── kinds.yml          # kind definitions + required fields
├── relations.yml      # relation vocabulary + target constraints
└── schema-notes.md    # section appended to _schema.md when pack is on
```

`kinds.yml` (japanese):

```yaml
kinds:
  grammar-point:
    path: grammar-point/
    fields:
      pattern: {required: true}      # "〜てから", "〜たら"
      meaning: {required: true}      # nghĩa tiếng Việt
      reading: {optional: true}
      register: {optional: true, enum: [casual, polite, formal, written]}
      jlpt: {optional: true, enum: [N5, N4, N3, N2, N1]}
      tags: {optional: true}
  vocab:
    path: vocab/
    fields:
      word: {required: true}
      reading: {required: true}
      meaning: {required: true}
      jlpt: {optional: true}
      register: {optional: true}
```

`relations.yml` (japanese):

```yaml
relations:
  contrast-with: {}
  example-of: {}
  synonym-of: {}
  derived-from: {}
  covered-in: {targets: [source]}     # only kind source
  related: {default: true}            # default for plain wikilinks
```

Core consumption:

- `ingest`/`reindex` load the pack for valid src paths + relation whitelist → validate edges before writing to `links`. **DB schema unchanged** — the pack only influences parser validation.
- Skill layer (ingest/query/lint) reads `kinds.yml` for slug rules and required fields.
- Wiki without `[langpack]` → parser skips packs entirely; zero behavior change.
- **Slug rule (japanese)**: grammar-point slugs derive from the normalized *pattern* (`ba-tara.md`, `te-kara.md`), never book+lesson. Book + lesson live in the source page + `covered-in` relation. Slug containing a textbook name → lint `style advisory`.

## 7. Ingest skill workflow (new synthesis step)

Edit `llm-wiki-base-ingest/SKILL.md`, inserted after the current dedupe-check step:

```
2.5. SYNTHESIS PASS — trước khi viết bất kỳ trang mới nào:
   a. Với mỗi grammar-point/vocab/concept chính trong raw: wiki_search tìm trang ĐÃ TỒN TẠI
      về cùng điểm ngữ pháp/từ (dùng pattern làm query, không dùng tên sách).
   b. Nếu trang đã có → KHÔNG tạo trang mới. Update trang cũ:
      - Thêm claim mới vào ## Claims kèm footnote nguồn MỚI (tăng provenance).
      - Thêm relations covered-in → source page của raw mới.
      - Ghi log.md: "synthesized into <page>".
   c. Nếu mâu thuẫn với claim cũ → giữ nguyên claim cũ, thêm rel: contradicts
      trỏ claim mới, mở wiki/alerts/ (không tự resolve).
   d. Slug rule: grammar-point slug theo pattern (ba-tara.md), TÊN SÁCH + BÀI
      chỉ sống trong source page + relation covered-in.
```

Profile page counts (`personal`: 10–15 pages/source) reworded: synthesis-in-place does not count against the quota.

## 8. Lint rules (deterministic, `tools/lint.py`)

| Rule | Severity | Auto-fix |
|---|---|---|
| `broken-relation-target` — dst missing | CRITICAL | no |
| `unknown-rel-type` — rel not in vocabulary/config/pack | CRITICAL | no |
| `langpack-field-missing` — required kind field absent (pack on) | CRITICAL | no |
| `claim-without-footnote` — bullet in `## Claims` without `[^id]` | CRITICAL | no |
| `relation-without-note` — contrast/contradicts without `note` | advisory | no |
| `inline-rel-vs-alias` — conflicting inline definitions | advisory | no |

All relation errors are AI/human fixes; only re-derivable content (index entries) remains `--fix`-able.

## 9. Testing (pytest, existing `tests/` conventions)

- `test_graph.py`: `extract_links` (frontmatter, inline, default wikilink edges, conflict dedup, `#claims` anchors), `sync_links` upsert + GC, pack validation, no-pack regression.
- Lint rule fixtures for each new rule.
- No `eval/golden.toml` changes (retrieval untouched).

## 10. Documentation deliverables

- **`docs/relations.md`** — user guide: full syntax (frontmatter + inline), `## Claims` convention, before/after worked Japanese example, enabling a langpack, graph query notes, migration notes ("old pages stay valid; add relations as consolidate touches them").
- **`docs/langpacks.md`** — creating a new pack; `kinds.yml`/`relations.yml` reference.
- **`templates/agents/_schema.md`** update + template `.llm-wiki-base.toml` update (`[langpack]`, commented by default).
- **Migration guide** for running wikis: re-run `llm-wiki-base init` to sync skills/schema, `reindex` to build `links`. Note: skill templates deploy into each wiki's `.agents/skills/` — requires version bump so old wikis pick them up.
- **AGENTS.md runbook** update: synthesis step in Operations → Ingest.

## 11. Risks / open questions

- AI consistency when authoring relations is enforced only by lint (unknown-rel-type, broken target) — acceptable given the propose/human-decide philosophy.
- `rel:` reserved prefix could collide with an existing alias literally starting with `rel:` — vanishingly rare; lint surfaces it (`inline-rel-vs-alias`).
- Anchor semantics (`#claims`) are section-level, not per-claim anchors; if per-claim precision becomes necessary later, add explicit claim ids then (roadmap).

## 12. Roadmap (explicitly out of scope)

- Graph-expand boost during query rerank (query skill reads `links`).
- Per-claim anchor ids.
- SRS/export integration (atomic claims are SRS-ready by construction).
