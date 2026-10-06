---
name: llm-wiki-base-translate
description: Translate 1 or more wiki pages into configured target languages. Uses the running AI tool's LLM (Claude Code → Claude, OpenCode → provider). Each translation is a mirror file under `wiki-<lang>/` (sibling of `wiki/`), excluded from DB/RAG. Use when the user says "translate page X to Vietnamese" or after ingest with target langs enabled.
id: 2d4debaf0830458a9efbe5b6cd4a068c
---

# llm-wiki-base Translate

Bilingual wikis: the canonical tree is `wiki/`; each target language gets a **parallel
tree** `wiki-<lang>/` that mirrors `wiki/` path-for-path:

```
wiki/<domain>/<kind>/<slug>.md   →   wiki-<lang>/<domain>/<kind>/<slug>.md
```

Translations:
- Same frontmatter keys as the source (`title`, `domain`, `kind`, `sources`, `updated`, `status`).
- Body 100% equivalent — no additions, no omissions, no paraphrasing.
- **Never indexed**: `wiki-<lang>/` is a sibling of `wiki/`, outside the index roots
  (`wiki/` + `raw/`), so BM25/RAG skip it automatically. Legacy inline `<slug>.<lang>.md`
  files (old layout) are still skipped by the CLI.

## Overview

Translates wiki pages into configured target languages using the running AI tool's LLM. Writes mirror pages under `wiki-<lang>/...`, verifies heading structure, and warns on high token cost. Always checks `llm-wiki-base translate status` before starting. Never modifies the source page. Never writes empty files. **Never translates Mermaid diagram files (`.mmd`) or Mermaid fenced blocks inside wiki pages.**

## LLM provider

**Use the running AI tool's LLM** — NEVER call a separate API (Claude Code → Claude, OpenCode → configured provider, Zed → configured provider). Env overrides (`LLM_WIKI_BASE_TRANSLATE_*`) are an optional bypass for dedicated OpenAI calls — ignore by default.

## Managing translation config

```bash
llm-wiki-base translate enable              # set enabled = true
llm-wiki-base translate disable             # set enabled = false (pauses without removing langs)
llm-wiki-base translate status              # show current config: enabled, langs, drift stats
llm-wiki-base translate check               # check all translations for drift
llm-wiki-base translate check --lang <code> # check drift for a specific lang
llm-wiki-base translate migrate --lang <code> # move legacy <slug>.<lang>.md → wiki-<lang>/
```

Always run `llm-wiki-base translate status` before invoking this skill.

## When

- The user says "translate page X to language Y".
- After ingesting a new source, if `.llm-wiki-base.toml` has `[translate].enabled = true` → the ingest skill auto-invokes this skill.
- Re-translate when source updates: `llm-wiki-base translate check --lang <code>` to detect drift.
- **Skip entirely** for `.mmd` files in `wiki/<domain>/diagrams/` — they contain Mermaid syntax, not natural language.

## Workflow

### 1. Determine target langs

Read `.llm-wiki-base.toml`. An explicitly requested lang wins. No target langs in config AND none requested → ask the user (suggest `llm-wiki-base translate enable`).

### 2. Per (source page, target lang)

**a** Read source page `wiki/<domain>/<kind>/<slug>.md`.

**b** Split frontmatter + body.

**c** Identify **untranslatable regions** in the body before translation:
   - Fenced code blocks of ANY language, including **`mermaid`** blocks — treated identically to code.
   - Wikilinks: `[[wiki/<domain>/...]]` — path preserved verbatim; alias text (if any) may be translated.
   - `<!-- diagram: diagrams/<slug>-N.mmd -->` comments — preserve **verbatim** (structural markers, not prose).
   - URLs, technical terms (class/function/package names, version numbers, env vars, flags).

**d** Translate body via the AI tool's LLM:

```
Translate the following markdown body to language code '<lang>'.
Rules:
- Translate natural-language text only.
- Preserve ALL of the following EXACTLY (character-for-character):
  - Fenced code blocks including ```mermaid blocks — DO NOT translate Mermaid syntax.
  - Wikilinks [[...]] path portions.
  - HTML comments <!-- ... --> verbatim.
  - URLs, package names, class/function names, version numbers, command flags.
- No additions, no omissions, no paraphrasing.
Output ONLY the translated body, no frontmatter, no commentary.

---
<body>
---
```

**e** Rejoin with original frontmatter verbatim (provenance, `updated`, `status` unchanged).

**f** Write the mirror path: `wiki-<lang>/<domain>/<kind>/<slug>.md` — the **same relative
path as the source**, only the tree root changes (`wiki/` → `wiki-<lang>/`). Create parent
directories as needed. Never write back into `wiki/`.

**g** Quick verify — all three checks must pass:
   - **Heading structure**: counts and levels must match source. Mismatch → retry once: *"Your previous translation changed the heading structure. Reproduce EXACTLY the same headings (count, level, order). Only translate heading text, not structure."*
   - **Mermaid blocks**: count must match source. Mismatch → retry once: *"Your previous translation dropped or altered a ```mermaid block. Keep every mermaid block 100% verbatim."*
   - **Diagram comments**: `<!-- diagram: ... -->` count must match source. Mismatch → retry once with the same instruction.
   - Still failing after one retry → flag to user, skip that file, **never write an incomplete file**.

### 3. After all translations

```bash
llm-wiki-base translate check --lang <code>
```

On mismatch → flag to user, don't self-fix.

## Ingest integration

When ingest writes a new source with `[translate].enabled = true`:
1. Ingest writes source page (EN) as usual.
2. Per lang in `langs`: invoke this workflow → `wiki-<lang>/<domain>/<kind>/<slug>.md`.
3. Reindex — translations (outside `wiki/`) and `.mmd` files auto-skip the DB/RAG.

**Cost note**: N sources × M langs = N×M LLM calls. Warn when: `len(langs) > 5` ("5+ target langs, token-heavy. Confirm?") or `N sources > 20` ("suggest batching in groups of 10").

## Migrating the old layout

Old wikis store translations inline as `wiki/**/<slug>.<lang>.md`. Move them to the mirror
tree once per lang (idempotent, never overwrites an existing target):

```bash
llm-wiki-base translate migrate --lang vi
```

Then re-run `llm-wiki-base translate check --lang vi` to confirm the mirror is complete.

## Constraints

- **One tree per lang** — `wiki-<lang>/` mirrors `wiki/`; never nest translations inside `wiki/`.
- **Never translate Mermaid fenced blocks** — they are code, not prose.
- **Never translate `.mmd` files** — skip them unconditionally; they are Mermaid source files.
- **Never translate `wiki/log.md`** — append-only history, language-agnostic.
- **Don't paraphrase** — translate natural text only.
- **Frontmatter verbatim** — `sources`, `updated`, `status` unchanged.
- **Heading structure preserved** — count + levels must match source.
- **Wikilinks preserved** — `[[wiki/<domain>/...]]` path unchanged; alias text may be translated.
- **Code blocks and HTML comments preserved** — kept 100% verbatim.

## Safety

- Never modify the source page.
- Malformed output → retry once with stricter prompt. Still failing → flag to user, skip that file, NEVER write an empty file.
- `enabled = false` AND none requested → skip silently.
- Always check the *current* `<wiki-root>/.llm-wiki-base.toml` — never another project's config.
