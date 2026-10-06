# Translation

Bilingual wikis: the canonical tree `wiki/` plus one **parallel tree per target
language**, `wiki-<lang>/`, mirroring `wiki/` path-for-path.

```
wiki/<domain>/<kind>/<slug>.md   ⇄   wiki-<lang>/<domain>/<kind>/<slug>.md
```

Translations **never enter DB/RAG**: `wiki-<lang>/` is a sibling of `wiki/`, so the
indexers (which scan `wiki/` + `raw/`) never see it. Legacy inline `<slug>.<lang>.md`
files are still skipped by the CLI.

```toml
# .llm-wiki-base.toml
[translate]
enabled = true
langs = ["vi", "ja"]        # → wiki-vi/, wiki-ja/
```

When enabled, the ingest skill calls skill `llm-wiki-base-translate` for every new
page. Translation uses **the running AI tool's LLM** — no separate API key, no
extra dependency in the Python pipeline.

```bash
llm-wiki-base translate enable --lang vi --lang ja   # written to .llm-wiki-base.toml (comments kept)
llm-wiki-base translate status                       # show state
llm-wiki-base translate disable                      # off, langs kept
llm-wiki-base translate check --lang vi              # verify wiki-vi/ mirrors wiki/
llm-wiki-base translate migrate --lang vi            # move legacy <slug>.vi.md → wiki-vi/
```
