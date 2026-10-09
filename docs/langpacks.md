# Language packs

A language pack is an optional, per-wiki folder of language-specific vocabulary:
page **kinds** with required frontmatter fields, a **relation vocabulary** with
target rules, and **schema notes** shown to the agent. Core stays
language-agnostic — a wiki without `[langpack]` sees **zero behavior change**
(the parser skips packs entirely).

## Enabling a pack

```toml
# .llm-wiki-base.toml
[langpack]
enabled = true
pack = "japanese"
```

- `enabled` falsy or `pack` empty → disabled (the default; the template
  `.llm-wiki-base.toml` ships this block commented out).
- `pack` must be a single folder name (no path separators, no `..`).
- Enabled but the folder is missing → **fail loud**, never silent: lint
  CRITICAL `langpack-config-error` listing the paths tried.
- After changing the block: `llm-wiki-base lint` (validation runs per command —
  there is no daemon to restart).

## Where packs load from

`templates/langpacks/<pack>/` is searched in order:

1. the installed package (`src/llm_wiki_base/` in a source checkout),
2. the global base `~/.llm-wiki-base/templates/langpacks/<pack>/` (root override:
   `LLM_WIKI_BASE_DIR`).

First folder containing **both** `kinds.yml` and `relations.yml` wins. The shipped
`japanese` pack lives in the package and is deployed into the global base by
`llm-wiki-base setup tools` — it is the canonical example:

```
templates/langpacks/japanese/
├── kinds.yml          # kinds + required fields
├── relations.yml      # relation vocabulary + target constraints
└── schema-notes.md    # pack's contribution to the wiki's _schema.md
```

## `kinds.yml` reference

Shape of the file — **abridged** example; the shipped pack
(`templates/langpacks/japanese/kinds.yml`) is the full field reference:

```yaml
kinds:
  grammar-point:
    path: grammar-point/
    fields:
      pattern: {required: true}      # "〜てから", "〜たら"
      meaning: {required: true}      # nghĩa tiếng Việt
      jlpt: {optional: true, enum: [N5, N4, N3, N2, N1]}
  vocab:
    path: vocab/
    fields:
      word: {required: true}
      reading: {required: true}
      meaning: {required: true}
```

- **`path`** — directory under each domain: any page whose path contains
  `/<path>/` (e.g. `wiki/languages/grammar-point/ba.md`) belongs to the kind.
- **`fields`** — the frontmatter contract for that kind:
  - `{required: true}` — field absent or empty → lint CRITICAL
    `langpack-field-missing` (no auto-fix; AI/human writes the value).
  - `{optional: true}` — allowed, otherwise unchecked.
  - `{optional: true, enum: [...]}` — declared allowed values. Lint checks
    *presence*, not membership; the enum table is surfaced to the authoring agent
    through `schema-notes.md`.
- The pack's slug rules also live in `schema-notes.md` (japanese: grammar-point
  slugs derive from the normalized **pattern** — `ba-tara.md`, `te-kara.md` —
  never book + lesson; a textbook name in a slug → style advisory).

## `relations.yml` reference

```yaml
relations:
  contrast-with: {}
  example-of: {}
  synonym-of: {}
  derived-from: {}
  covered-in: {targets: [source]}     # only kind source
  related: {default: true}            # default for plain wikilinks
```

- **key** = relation type (kebab-case); **value**:
  - `{}` — free relation: any target kind.
  - `targets: [<path>, …]` — the target must pass through one of those kind
    directories (`covered-in` → dst must contain `/source/`); violation → lint
    CRITICAL `relation-target-kind`.
  - `default: true` — marks the relation plain `[[path]]` links resolve to. The
    core default is always `related`; declaring it keeps the pack
    self-documenting.
- A rel **not** in the pack (and not core) → lint CRITICAL `unknown-rel-type`.
- **Core rels are always allowed**: `related` (default wikilink edge) and
  `contradicts` (claim-vs-claim) are language-independent and valid whether or
  not the pack lists them — the pack vocabulary is a **union** on top, never a
  replacement.

## Adding a new pack

1. **Copy the japanese pack** and rename it:
   - source checkout: `cp -r src/llm_wiki_base/templates/langpacks/japanese src/llm_wiki_base/templates/langpacks/<your-pack>`
   - installed tool: create `~/.llm-wiki-base/templates/langpacks/<your-pack>/` instead (the global base is a valid lookup location on its own).
2. **Edit** `kinds.yml` (kinds, paths, fields), `relations.yml` (vocabulary,
   target constraints), `schema-notes.md` (field tables, slug rule, relation
   vocabulary, claim examples — this is what the agent reads).
3. **Point the wiki at it** — `[langpack] pack = "<your-pack>"` in
   `.llm-wiki-base.toml` — then run `llm-wiki-base lint` and
   `llm-wiki-base reindex`. Each command is a fresh process, so the YAML reloads
   on the next run; nothing else to restart.

Ship-worthy packs belong in the package tree (`src/llm_wiki_base/templates/langpacks/`)
so `llm-wiki-base setup tools` deploys them to every machine's global base.

Related: [relations.md](relations.md) (user-facing syntax) ·
[migration-relations.md](migration-relations.md) (per-wiki upgrade).
