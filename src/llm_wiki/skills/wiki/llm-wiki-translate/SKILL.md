---
name: llm-wiki-translate
description: Translate 1 or more wiki pages into configured target languages. Uses the running AI tool's LLM (Claude Code → Claude, OpenCode → provider). Translations are parallel <slug>.<lang>.md files, excluded from DB/RAG. Use when the user says "translate page X to Vietnamese" or after ingest with target langs enabled.
---

# llm-wiki Translate

Bilingual wikis: each source page `wiki/<domain>/<kind>/<slug>.md` may have a parallel translation `wiki/<domain>/<kind>/<slug>.<lang>.md`. Translations:
- Same frontmatter keys as the source (`title`, `domain`, `kind`, `sources`, `updated`, `status`).
- Body 100% equivalent — no additions, no omissions, no paraphrasing.
- **Excluded from DB/RAG** (skip rule `*.lang.md` in `tools/{ingest,reindex,watch}.py` + `rag/index.py`).

## LLM provider

**Use the running AI tool's LLM** — NEVER call a separate API:
- Claude Code → Claude (claude-sonnet-4-5 or the session's current model).
- OpenCode → the provider configured in `opencode.json`.
- Zed → the configured provider.

Env `LLM_WIKI_TRANSLATE_API_KEY` / `LLM_WIKI_TRANSLATE_BASE_URL` / `LLM_WIKI_TRANSLATE_MODEL` is an **OPTIONAL bypass** — only if the user wants a dedicated OpenAI API call instead of the AI tool LLM. Ignore by default.

## When

- The user says "translate page X to language Y".
- After ingesting a new source, if `.llm-wiki.toml` has `[translate].enabled = true` → the ingest skill auto-invokes this skill per target lang.
- Re-translate when the source updates: run `llm-wiki translate check --lang <code>` to detect drift, then re-invoke this skill for mismatched files.

## Workflow

### 1. Determine target langs

Read `.llm-wiki.toml` at the wiki root:

```toml
[translate]
enabled = true
langs = ["vi", "ja"]
```

An explicitly requested lang wins → use it, ignore config. No target langs in config AND none requested → ask the user.

### 2. Per (source page, target lang) to translate

**Step a**: Read the source page `wiki/<domain>/<kind>/<slug>.md`.

**Step b**: Split frontmatter (between the two `---` lines) + body.

**Step c**: Have the current AI tool's LLM translate the body. Standard prompt:

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

**Step d**: Rejoin with the original frontmatter verbatim (translations share `sources`, `kind`, `updated` so provenance stays intact). Output: the complete file.

**Step e**: Write `wiki/<domain>/<kind>/<slug>.<lang>.md`.

**Step f** (quick verify): check heading counts match the source. Mismatch → retry once with a stricter prompt: "Your previous translation added/removed headings. Try again, output EXACTLY the same heading structure as input."

### 3. After all translations

Run:

```bash
llm-wiki translate check --lang <code>
```

On mismatch → flag to the user, don't self-fix. Common causes: LLM paraphrase, LLM added/dropped headings, source updated after translating.

## Ingest integration

When the ingest skill writes a new source and `.llm-wiki.toml` has `[translate].enabled = true`:
1. Ingest writes the source (EN) → `wiki/<domain>/source/<slug>.md` (as usual).
2. Per lang in `langs`: invoke the workflow above to create `<slug>.<lang>.md`.
3. After ingest, reindex — translations auto-skip the DB.

**Cost note**: ingesting N sources × M langs = N×M LLM calls. Warn the user when:
- `len(langs) > 5` → "5+ target langs, token-heavy. Confirm continue?"
- `N sources > 20` → "20+ sources, suggest ingesting in batches."

## Constraints

- **Don't translate code blocks, URLs, technical terms** (class names, function names, package names, version numbers, command flags, env vars).
- **Don't paraphrase** — translate natural text only. Markdown structure preserved 100%.
- **Don't editorialize** — a terse source gets an equally terse translation.
- **Frontmatter verbatim** — `sources` (provenance), `updated`, `status` do NOT change.
- **Heading structure preserved** — heading count + levels + text must match the source (verified by `llm-wiki translate check`).
- **Wikilinks preserved** — `[[wiki/<domain>/...]]` keeps its path; do NOT localize alias text (so Obsidian resolves the path correctly).
- **Code blocks** — kept 100% (don't even translate code comments).

## Safety

- Translations are parallel files; never modify the source.
- Malformed LLM output (missing markdown, added preamble/suffix) → retry once with a stricter prompt. Still failing → flag to the user, skip that file, NEVER write an empty file.
- No target langs configured (`enabled = false` or file missing) AND none requested → do NOT translate, do NOT ask further (skip silently). Unless the user explicitly says "translate to language X".
- Cross-wiki contamination: in a different project wiki (multi-project), check the *current* `<wiki-root>/.llm-wiki.toml`, NEVER another project's config.
