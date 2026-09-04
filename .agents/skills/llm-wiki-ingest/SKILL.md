---
name: llm-wiki-ingest
description: >
  Feed one raw source into the wiki and integrate it as concepts — auto-detect domain, read,
  summarize, cross-link entity/concept, update index/log, incremental reindex. Use when a new
  file lands in raw/inbox/ or when the human says "ingest", "take in this source". Runs for
  both personal and codebase wikis (reads [wiki].profile).
---

# LLM Wiki — Ingest

Turn raw sources into/updated concepts: keep provenance, don't break human content, and keep the search index in sync immediately.

Schema: `_schema.md`. Runbook: `AGENTS.md`. Related: `llm-wiki-query` (uses the knowledge), `llm-wiki-lint` + `llm-wiki-review` (verify afterwards), `llm-wiki-reindex` (index rebuild only).

## Profile — read first

Read `[wiki].profile` in `<wiki_root>/.llm-wiki.toml`:

| | `personal` | `codebase` |
|---|---|---|
| wiki root | standalone wiki folder | `<project>/<wiki-dir>/` (e.g. `project-wiki/`) |
| touches per source | **10–15 pages** (wiki grows by topic) | **5–10 pages** (more focused) |
| typical domains | free-form by topic | `tech-stack`, `architecture`, `conventions`, `dependencies`, `deployment`, `testing`, `security`, `api`, `data-model`, `domain/<sub>` |
| content language | grammar/patterns + vocabulary must enter the wiki, not die in the source page | code paths must be **verified** before writing |

Marks **[personal]** / **[codebase]** below apply to that profile only.

## When

A new source lands in `raw/inbox/` — dropped by a human, produced by `scripts/extract_*.py`, OR **submitted by another AI via MCP `wiki_submit`** (docs, PRs, architecture notes, projects). The human says "ingest this".

## Process

1. **Read the source**: `read_raw_source(name, "inbox", wiki=<wiki name>)` or `wiki_read("raw/inbox/<name>", wiki=<wiki name>)`.
   - Wiki name: `llm-wiki wiki list`. `wiki=""` = cross-wiki (only when you genuinely need a source from another wiki).
   - Ambiguous content / not enough context to settle takeaways → `websearch` the URL or citation in the raw's `source` field before asking the human. **Never guess blind.**
2. **Discuss short takeaways with the human** (default: ingest one source at a time).
3. **Auto-detect domain** (top-level folder under `wiki/`):
   - Read content + URL + title → determine topic. Matching folder exists → use it.
   - None matches → create a new folder per the naming rule (kebab-case, lowercase, ASCII-safe) + empty `wiki/<domain>/index.md` (filled in step 7).
   - **[codebase]** Intent (requirements, decisions) ≠ observation (behavior read from code) — don't mix both in one page; unclear intent → record an open question, **don't invent requirements**.
4. **Write the summary page** → `wiki/<domain>/source/<slug>.md`.
   - REQUIRED frontmatter: `title`, `domain: <domain>`, `kind: source`, `sources`, `updated`, `status: active`, `generated: {by: "<tool>/<model>", at: <ISO-8601 with offset>}`.
   - **Do NOT set `verified`** — wait for human artifact review (`llm-wiki verify <path> --by <id>`, same mechanism for both profiles; see `_schema.md` Trust tier).
   - `sources:` prefers list-of-dicts + per-claim citation:
     ```yaml
     sources:
       - id: s1
         resource: <url-or-wiki-xref-or-raw-path>
         title: "..."
     ```
     Body cites: `Important takeaway.[^s1]` + closing footnote with a **verbatim quote** from raw. Flat list `sources: [<url>]` stays valid (legacy) when a page needs no per-claim citation.
   - `sources:` rules: original URL exists → `resource: <url>` (URL is primary provenance); no URL → a source page in the domain is the provenance. **NEVER** write `raw/inbox/...` (staging, path changes → drift). `raw/` outside inbox = local cache, citable if the user wants.
   - **NEVER** write `[[raw/inbox/...]]` in body — local links only in `sources:`. `[[raw/...]]` outside inbox: allowed.
   - **[codebase]** Body should reference code paths where applicable (`src/auth/middleware.ts`, `tests/auth.test.ts`) — inline code or wikilink.
   - **[personal]** Languages domain: grammar/patterns → dedicated concept pages (`wiki/<domain>/concept/<pattern>.md`, 1 pattern = 1 page when possible); vocabulary → collect in `wiki/<domain>/vocab/<slug>.md` (table: word · reading · meaning · example) or extend an existing entity/concept.
5. **Create/update related entity + concept pages** in the **same domain**, cross-linked `[[wiki/<domain>/...]]`.
   - **Anti-fork**: before creating, search the DB (`wiki_list` / `wiki_search`) for a `status: planned` page on the topic → **update** if found, don't create. Complete page → `planned → active`.
   - **Pins** (`wiki/pins.yml`): an `active` pin anchored to a section of a page you're editing → do NOT overwrite that section. A new source contradicting a pin → record a gap in `wiki/alerts/` (frontmatter `domain: alerts, kind: alert, status: open`), **never revert silently**.
   - Every new page needs at least 1 outbound wikilink (or `llm-wiki-lint` will flag it orphan).
   - **[codebase]** kinds: `entity` = library/framework/tool/dependency (`wiki/tech-stack/entity/react-query.md`); `concept` = pattern/architecture/layer (`wiki/architecture/concept/middleware-chain.md`); `source` = doc summary; `task` = task tracking.
6. **Auto-translation (if enabled)**: read `<wiki_root>/.llm-wiki.toml`. If `[translate].enabled = true` and `langs` is non-empty:
   - For each page just created (new source + entity/concept), call skill **`llm-wiki-translate`** → parallel `<slug>.<lang>.md`.
   - **Do NOT translate** inside ingest — let the translate skill use the running AI tool's LLM.
   - Translations are parallel files, don't touch the source; auto-skipped from DB/RAG (`*.lang.md` rule).
   - `len(langs) > 5` or new pages > 20 → warn about token cost before calling the skill.
   - No `.llm-wiki.toml` or `enabled = false` → skip silently.
7. Update `wiki/<domain>/index.md` (add entries under Entity / Concept / Source / Task). **New domain** → add a row to `wiki/index.md` (top-level) + insert a "→ [domain/index.md]" line right after the header.
8. Insert into `wiki/log.md` (reverse-chronological: newest on top): `## [YYYY-MM-DD HH:MM:SS] ingest | <title>` + lines of changes.
   - **Date = `updated` from the just-written source page's frontmatter** (not today). Fallback: `stat -f %Sm` (macOS) / file mtime. Time = `date +%H:%M:%S` at ingest time, to disambiguate same-day entries.
   - Position: larger timestamp → inserted before smaller ones (closest to header). Same day → compare full `YYYY-MM-DD HH:MM:SS`.
   - Use **Edit anchored at the next entry** for exact insertion — **NEVER `Write`-rewrite the whole file, NEVER `cat >>`** (rewriting the log destroys history).
9. **Reindex now** (incremental, run inside `<wiki_root>`):
   ```bash
   llm-wiki reindex
   ```
   Only created/edited files get re-indexed (content-hash). `*.lang.md` translations + `index.md`/`log.md` auto-skip the chunk index. `llm-wiki reindex --check` = dry-run; `--full` when `chunk_tokens`/`embed_model`/`vector`/`fusion` change. Detail: `llm-wiki-reindex` skill.
10. **Move the source out of inbox**: `mv <wiki_root>/raw/inbox/<name> <wiki_root>/raw/<name>` — a URL in `source` means raw is just gitignored local cache (real provenance sits in the URL); no URL means this is the only copy, think before letting the user delete it.
11. **Verify**: `llm-wiki reindex && llm-wiki lint`, or find the page via MCP `wiki_search`. Report: concepts created/edited, what got reindexed, and what **needs human review**.

## MCP tools (bridge for other AIs)

- Intake: `wiki_submit(title, content, wiki, domain, source)` → writes to the **human-designated** wiki's `raw/inbox/`. Other AIs must NOT write `wiki/` directly. `domain` optional (blank = maintainer detects in step 3).
- Read: `read_raw_source` · `wiki_read(path, wiki)` · `wiki_list(domain=…, kind=concept, wiki)`.
- Propose (staging): `wiki_propose_edit(path, content, wiki)` → `wiki/.proposals/`, awaiting `llm-wiki proposals apply|discard`. **Stating `wiki` is mandatory** on write.
- **Indexing/ingesting is maintainer work via CLI**, NOT via MCP writes.

## Safety

- Writing wiki pages / index / log is re-derivable → the agent writes directly. Any other claim needs provenance (`[[link]]` or URL in `sources:`).
- **Raw is immutable** — never edit source files. Raw local cache (gitignored) may be deleted by the user at will; the URL in `sources:` is the primary provenance.
- **[codebase] Code paths must be verified**: before writing `src/foo/bar.ts` into the wiki, confirm the file exists via `grep` (or the codegraph plugin at the repo root, if installed). A wiki stale on code paths is the worst project-wiki failure.
- **[codebase] Wiki ↔ code contradiction** → flag the human, fix neither code nor wiki yourself.
- **Copied state**: pages hold NO moveable values (SHA, mtime, line count, absolute counts). Values live in frontmatter or are read live from tooling.
- Never set `verified` on behalf of a human.
