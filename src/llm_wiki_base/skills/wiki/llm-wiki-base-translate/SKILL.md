---
name: llm-wiki-base-translate
description: Translate 1 or more wiki pages into configured target languages. Uses the running AI tool's LLM (Claude Code → Claude, OpenCode → provider). Translations are parallel <slug>.<lang>.md files, excluded from DB/RAG. Use when the user says "translate page X to Vietnamese" or after ingest with target langs enabled.
id: 2d4debaf0830458a9efbe5b6cd4a068c
---

# llm-wiki-base Translate

Bilingual wikis: each source page `wiki/<domain>/<kind>/<slug>.md` may have a parallel translation `wiki/<domain>/<kind>/<slug>.<lang>.md`. Translations:
- Same frontmatter keys as the source (`title`, `domain`, `kind`, `sources`, `updated`, `status`).
- Body 100% equivalent — no additions, no omissions, no paraphrasing.
- **Excluded from DB/RAG** (`*.lang.md` skip rule in `tools/{ingest,reindex,watch}.py` + `rag/index.py`).

## Overview

Translates wiki pages into configured target languages using the running AI tool's LLM. Writes parallel `<slug>.<lang>.md` files, verifies heading structure, and warns on high token cost. Always checks `llm-wiki-base translate status` before starting. Never modifies the source page. Never writes empty files.

## LLM provider

**Use the running AI tool's LLM** — NEVER call a separate API (Claude Code → Claude, OpenCode → configured provider, Zed → configured provider). Env overrides (`LLM_WIKI_BASE_TRANSLATE_*`) are an optional bypass for dedicated OpenAI calls — ignore by default.

## Managing translation config

```bash
llm-wiki-base translate enable              # set enabled = true
llm-wiki-base translate disable             # set enabled = false (pauses without removing langs)
llm-wiki-base translate status              # show current config: enabled, langs, drift stats
llm-wiki-base translate check               # check all translations for drift
llm-wiki-base translate check --lang <code> # check drift for a specific lang
```

Always run `llm-wiki-base translate status` before invoking this skill.

## When

- The user says "translate page X to language Y".
- After ingesting a new source, if `.llm-wiki-base.toml` has `[translate].enabled = true` → the ingest skill auto-invokes this skill.
- Re-translate when source updates: `llm-wiki-base translate check --lang <code>` to detect drift.

## Workflow

### 1. Determine target langs

Read `.llm-wiki-base.toml`. An explicitly requested lang wins. No target langs in config AND none requested → ask the user (suggest `llm-wiki-base translate enable`).

### 2. Per (source page, target lang)

**a** Read source page `wiki/<domain>/<kind>/<slug>.md`.

**b** Split frontmatter + body.

**c** Translate body via the AI tool's LLM:

```
Translate the following markdown body to language code '<lang>'.
Preserve all markdown structure, code blocks, wikilinks [[...]], and links [text](url) exactly.
Translation must be 100% equivalent — no additions, no omissions, no paraphrasing.
Do NOT translate code blocks, URLs, or technical terms (class/function/package names, version numbers, command flags).
Output ONLY the translated body, no frontmatter, no commentary.

---
<body>
---
```

**d** Rejoin with original frontmatter verbatim (provenance, `updated`, `status` unchanged).

**e** Write `wiki/<domain>/<kind>/<slug>.<lang>.md`.

**f** Quick verify: heading counts must match source. Mismatch → retry once: "Your previous translation added/removed headings. Try again, EXACTLY the same heading structure."

### 3. After all translations

```bash
llm-wiki-base translate check --lang <code>
```

On mismatch → flag to user, don't self-fix.

## Ingest integration

When ingest writes a new source with `[translate].enabled = true`:
1. Ingest writes source page (EN) as usual.
2. Per lang in `langs`: invoke this workflow → `<slug>.<lang>.md`.
3. Reindex — translations auto-skip the DB.

**Cost note**: N sources × M langs = N×M LLM calls. Warn when: `len(langs) > 5` ("5+ target langs, token-heavy. Confirm?") or `N sources > 20` ("suggest batching").

## Constraints

- **Don't translate code blocks, URLs, technical terms** (class/function names, package names, version numbers, flags, env vars).
- **Don't paraphrase** — translate natural text only.
- **Frontmatter verbatim** — `sources`, `updated`, `status` unchanged.
- **Heading structure preserved** — count + levels + text must match source.
- **Wikilinks preserved** — `[[wiki/<domain>/...]]` path unchanged; don't localize alias text.
- **Code blocks** — kept 100%.

## Safety

- Never modify the source page.
- Malformed output → retry once with stricter prompt. Still failing → flag to user, skip that file, NEVER write an empty file.
- `enabled = false` AND none requested → skip silently.
- Always check the *current* `<wiki-root>/.llm-wiki-base.toml` — never another project's config.
