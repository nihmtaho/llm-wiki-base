<!-- LLM_WIKI_RESEARCH_START -->
## LLM Wiki Research

In repositories with a project wiki (a `.agents/skills/llm-wiki-research/` directory exists at the repo root), research curated knowledge BEFORE grep/find when the answer may already be compiled:

- **Skill** (when available): `/llm-wiki-research <question>` — cross-wiki search via MCP `llm-wiki-base-mcp` (`wiki_search` with `wiki=""` = all wikis). Every result carries a `wiki` field — read it before citing, or you'll attribute personal knowledge to the project.
- **Shell** (always works): `llm-wiki wiki list` shows known wikis (name + type + path); `registry://wikis`, `wiki://<name>/index`, `wiki://<name>/log` give TOC + history.
- **Boundary**: `research` = many wikis (find + contrast, staging-only writes via `wiki_submit` / `wiki_propose_edit`); `query` = one wiki you stand in (answer + write synthesis). If you already know which wiki holds the answer, don't go cross-wiki.
- **Trust**: a page from a different-type wiki (personal ↔ codebase) is context, not this repo's truth; wikis can go stale against code — cross-check critical claims against code; contradictions → report to the human, never self-resolve. Never cite `raw/` as evidence (deletable cache; real provenance is the URL in `sources:`).

If there is no `.agents/skills/llm-wiki-research/` directory, skip this entirely — wiki setup is the user's decision.
<!-- LLM_WIKI_RESEARCH_END -->
