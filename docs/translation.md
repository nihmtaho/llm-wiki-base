# Translation

Bilingual wikis: one source page + 1+ translations `<slug>.<lang>.md`.
Translations **never enter DB/RAG** (skip rule `*.lang.md`), so they never
compete with the source in search.

```toml
# .llm-wiki.toml
[translate]
enabled = true
langs = ["vi", "ja"]
```

When enabled, the ingest skill calls skill `llm-wiki-translate` for every new
page. Translation uses **the running AI tool's LLM** — no separate API key, no
extra dependency in the Python pipeline.

```bash
llm-wiki translate enable --lang vi --lang ja   # written to .llm-wiki.toml (comments kept)
llm-wiki translate status                       # show state
llm-wiki translate disable                      # off, langs kept
llm-wiki translate check --lang vi              # verify frontmatter + heading sync
```
