# MCP bridge

MCP is a **bridge** for AI tools — not a channel for writing to the wiki
directly.

| Tool | Role |
|---|---|
| `wiki_search(query, top_k, wiki)` | Union retrieval + RRF: `bm25_page` ∪ `bm25_chunk` ∪ `vector_chunk`; each hit has `matched_by` + `rank` + `snippet`. `top_k = 0` → follows `top_n_final` |
| `semantic_search(query, top_k, wiki)` | Raw chunk-level vector search (concept finding only, not an answer source) |
| `wiki_read(path, wiki)` | Read one file |
| `wiki_list(domain, kind, wiki)` | List pages, with filters |
| `list_raw_source(subdir, wiki)` | List files in `raw/` |
| `read_raw_source(name, subdir, wiki)` | Read a raw source |
| `wiki_submit(title, content, wiki, …)` | **Write into `raw/inbox/`** — the only intake gate, `wiki` required |
| `wiki_propose_edit(path, content, wiki)` | Stage into `wiki/.proposals/` (with target metadata) |
| `wiki_lint(wiki)` | Deterministic health-check |

Resources: `registry://wikis`, `wiki://<name>/index`, `wiki://<name>/log`.
Rerank is **not an MCP tool** — it's the LLM step inside skill
`llm-wiki-base-query` / `llm-wiki-base-research`.

## Per-client setup (`llm-wiki-base init -c …`)

Always written into the per-project/personal wiki MCP file (committable to VCS,
shared by the whole team):

| client | file (in wiki/repo) | key |
|---|---|---|
| `claude` | `<root>/.mcp.json` | `mcpServers` |
| `commandcode` | `<root>/.mcp.json` | `mcpServers` |
| `opencode` | `<root>/opencode.jsonc` | `mcp` |
| `zed` | no project-scope file → init reports skipped | `context_servers` |

The entry points at `["llm-wiki-base", "serve", "--mcp"]` (like
`codegraph serve --mcp`) — `llm-wiki-base` must be on PATH so agents can launch the
server (`sudo ln -s "$(pwd)/.venv/bin/llm-wiki-base" /usr/local/bin/llm-wiki-base`).

Restart the AI tool after init — the old MCP process keeps `registry.toml` in
memory.

## Skill distribution

`.agents/skills/` is the single canonical copy:

| `--skills-target` | result |
|---|---|
| `universal` (default) | copy into `.agents/skills/` + symlink for clients passed via `-c` |
| `claude` | as above + guaranteed `.claude/skills/` link |
| `both` | links for both `.claude/skills/` and `.opencode/commands/` |
| `skip` | no install (`--no-skills`) |

- **Command Code** reads `.agents/skills/` (project) and `~/.agents/skills/`
  (user) directly → no links needed. Creating `.commandcode/skills/` takes
  precedence over `.agents/` and raises duplicate-name warnings when the two
  copies drift.
- **Claude Code**: dir symlink `.claude/skills/<name>` → `.agents/skills/<name>`.
- **OpenCode**: file symlink `.opencode/commands/<name>.md` → `.agents/skills/<name>/SKILL.md`.
- **Zed**: no skill system (MCP only).
- Windows without symlink rights → automatic copy fallback.
