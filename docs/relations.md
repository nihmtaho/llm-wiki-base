# Typed relations & claims

A plain wikilink says *that* two pages are connected — never *how*. Typed relations
record the connection itself (`contrast-with`, `example-of`, `covered-in`, …) as
structured data, and the `## Claims` convention breaks page prose into atomic,
individually-cited statements. Both are extracted **deterministically** (no LLM,
same contract as chunking) into a `links` table during `reindex`, so lint can check
them and a later ingest can *update* an existing page when a new source touches the
same knowledge — instead of forking a second page. Pages written before this feature
stay valid untouched.

Full contract: your wiki's `_schema.md` → **Relations & Claims**.

## Frontmatter `relations:` (primary)

```yaml
relations:
  - rel: contrast-with
    target: wiki/languages/grammar-point/ba.md
    note: "〜たら nhấn hậu quả tình cờ"
    source: s1        # optional — footnote id in sources:
```

| field | required | meaning |
|---|---|---|
| `rel` | yes | relation type |
| `target` | yes | full path of the target page; `#anchor` allowed |
| `note` | no | one line of context stored on the edge |
| `source` | no | footnote id in `sources:` this edge is grounded in |

- Without a langpack, `rel` is free text — lint can't check the vocabulary. With a
  pack on, unknown types are CRITICAL (`unknown-rel-type`); see
  [langpacks.md](langpacks.md). Core types `related` + `contradicts` are always
  allowed.
- `contrast-with` / `contradicts` without a `note` → lint advisory
  (`relation-without-note`): a contrast nobody can read is a contrast nobody trusts.
- Be consistent with the target form — the stored `dst` is the literal path you
  write (this guide and `_schema.md` use the `.md` form for typed targets).

## Inline typed wikilinks (supplementary)

For an edge that belongs where the prose is:

```
[[wiki/languages/grammar-point/ba.md|rel:contrast-with]]
[[wiki/languages/grammar-point/ba.md|rel:example-of|Ví dụ của 〜たら]]
```

- **`rel:` is a reserved alias prefix.** An alias starting with `rel:` is parsed as
  a typed edge, never as display text — don't use it for ordinary labels.
- Conflicting definitions of the same target (two different rels), or a normal
  alias that merely *looks* like a rel name → lint advisory `inline-rel-vs-alias`.
- Links inside code fences and inline code spans are ignored (same as lint).

## Default edges & dedup priority

- Plain `[[path]]` → edge `rel: related`; `[[path|alias]]` → `related` with the
  alias kept as the edge note. Orphan detection and graph continuity are unchanged.
- The same relation (rel + target) declared more than once is stored once —
  priority **frontmatter > inline > wikilink**; the frontmatter `note` wins on
  conflict. A typed edge and the default `related` edge to the same page are
  *different* relations, so both are kept.
- Everything lands in the `links` table (`src`, `rel`, `dst`, `note`, `origin`) —
  queryable with plain SQL. Retrieval-side graph expansion is roadmap, not shipped.
- Edit a page → `llm-wiki-base reindex` re-syncs just that page's edges;
  `llm-wiki-base reindex --full` rebuilds the whole table.

## `## Claims` — atomic facts

```markdown
## Claims

- 〜たら dùng để chỉ việc "sau khi X xảy thì Y" với sắc thái tình cờ, không chủ đích.[^s1]
- Shinkanzen N3 bài 6 xếp 〜たら vào nhóm điều kiện, không nhóm "sau khi".[^s1]
```

- One bullet = one claim atom = exactly one sentence, ≥1 footnote `[^id]`
  resolving to an id in `sources:`. No multi-idea bullets. Footnotes keep their
  verbatim-quote semantics; claims *organize* the citation system, they don't
  replace it.
- A bullet with no footnote → lint CRITICAL `claim-without-footnote`.
- Claims are prose content, **not** a new page kind.
- **Claim vs claim** — point a typed link at the other page's `## Claims` section:

  ```markdown
  - 〜ば nhấn điều kiện logic.[^s2] [[wiki/languages/grammar-point/ba.md#claims|rel:contradicts]]
  ```

  The parser scans the target's `## Claims` section; the owning bullet's text
  becomes the edge's `note`.
- **Contradiction policy**: a new source that *agrees* with an existing claim →
  add a new footnote to that claim (more provenance). A new source that
  *contradicts* → **never edit the old claim**: add `rel: contradicts` + open
  `wiki/alerts/` (`status: open`). Contradictions are resolved by a human, never
  automatically.

## Enabling the japanese language pack

```toml
# .llm-wiki-base.toml
[langpack]
enabled = true
pack = "japanese"
```

Adds the `grammar-point/` + `vocab/` kinds (with required fields), the pack's
relation vocabulary, and the pattern-slug rule; core `related` + `contradicts`
stay valid. Run `llm-wiki-base lint` after enabling — new checks:
`langpack-field-missing`, `unknown-rel-type`, `relation-target-kind` (plus
`langpack-config-error` if the pack can't be loaded). Wikis
without `[langpack]` are 100% unaffected. Full pack reference:
[langpacks.md](langpacks.md).

## Worked example — 〜たら vs 〜ば (japanese wiki)

### Before: forked per textbook

The same 〜たら knowledge lives on two book-scoped pages, `sources: []`, tied only
by bare wikilinks:

- `wiki/languages/concept/shinkanzen-n3-bai-6-ba-tara-nara-to.md` — 〜ば・〜たら・〜なら・〜と
  (Shinkanzen N3 bài 6)
- `wiki/languages/concept/minna-no-nihongo-bai-26-tara-ii.md` — 疑問詞 + Vたらいい
  (Minna no Nihongo bài 26)

Each ends with a bare `## Liên kết` pointing at its own source page (neither page
links the other):

```markdown
## Liên kết
- [[wiki/languages/source/shinkanzen-n3-bai-6-ngu-phap]]   # on the shinkanzen page
- [[wiki/languages/source/minna-no-nihongo-bai-26-ngu-phap]] # on the minna page
```

Slugs are book + lesson, so the next textbook forks the pattern *again*; the edges
are untyped (a machine can't tell "covered-in" from "related"); statements are
buried in prose with no per-claim provenance.

### After: one page per pattern

One canonical `wiki/languages/grammar-point/ba-tara.md` (slug from the **pattern**,
never the book — textbook + lesson live in the source pages, reached via
`covered-in`):

```markdown
---
title: "〜たら — điều kiện / sau khi"
domain: languages
kind: grammar-point
pattern: 〜たら
meaning: "nếu ~ thì / sau khi ~ thì"
jlpt: N3
sources:
  - id: s1
    resource: wiki/languages/source/shinkanzen-n3-bai-6-ngu-phap.md
    title: "Shinkanzen N3 Bài 6 — Ngữ pháp"
  - id: s2
    resource: wiki/languages/source/minna-no-nihongo-bai-26-ngu-phap.md
    title: "Minna no Nihongo Bài 26 — Ngữ pháp"
updated: 2026-10-09
status: active
relations:
  - rel: covered-in
    target: wiki/languages/source/shinkanzen-n3-bai-6-ngu-phap.md
    note: "Bài 6 — so sánh ば/たら/なら/と"
    source: s1
  - rel: covered-in
    target: wiki/languages/source/minna-no-nihongo-bai-26-ngu-phap.md
    note: "Bài 26 — 疑問詞 + Vたらいい"
    source: s2
---

## Claims

- 〜たら dùng cho "sau khi X xảy thì Y", sắc thái tình cờ.[^s1]
- 〜たら thay thế 〜ば cho điều kiện tương lai trong văn nói.[^s1]
- 疑問詞 + Vたらいいですか là một cách dùng của 〜たら (xin lời khuyên).[^s2]
```

(Footnote definitions `[^s1]:` / `[^s2]:` follow the normal citation flow —
omitted here for brevity.)

What this buys: one page per pattern; `covered-in` edges name both books
(provenance-granular); when the next textbook covers 〜たら, the ingest skill's
synthesis pass appends a new claim + footnote (or a `contradicts` edge + an alert)
instead of forking a third page. The old book-scoped concept pages fold into the
canonical page through consolidate's normal duplicate handling (`superseded`).

## Migration

**Old pages stay valid — no backfill required.** Add `relations:` / `## Claims`
incrementally, whenever consolidate or review already touches a page. Upgrading a
running wiki: [migration-relations.md](migration-relations.md). Packs:
[langpacks.md](langpacks.md).
