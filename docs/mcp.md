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

## Per-client setup (`llm-wiki-base setup -c …`)

`setup` asks which clients to install into with a checkbox menu, **pre-checked to
the clients it can prove are on this machine** (binary on PATH, config dir, or
macOS app bundle). See what it found without running the wizard:

```bash
llm-wiki-base setup clients      # table: client | installed | evidence | writes
llm-wiki-base --help             # or `setup doctor` for the same table + health checks
```

`-c` is repeatable and optional. Omit every `-c` to mean "the detected ones";
pass any `-c` to mean "exactly these, don't guess".

| client | file | key | note |
|---|---|---|---|
| `claude` | `<root>/.mcp.json` | `mcpServers` | |
| `commandcode` | `<root>/.mcp.json` | `mcpServers` | same file as `claude` |
| `pi` | `<root>/.mcp.json` | `mcpServers` | same file; needs `pi install npm:pi-mcp-adapter` |
| `opencode` | `<root>/opencode.jsonc` | `mcp` | |
| `zed` | `<root>/.zed/settings.json` | `context_servers` | project settings |
| `cursor` | `<root>/.cursor/mcp.json` | `mcpServers` | entry carries `type: "stdio"`, no `cwd` |
| `copilot` | `<root>/.vscode/mcp.json` | `servers` | VS Code / Copilot Chat; key is NOT `mcpServers` |
| `codex` | `<root>/.codex/config.toml` | `[mcp_servers.<name>]` | **TOML**, written as a managed block; Codex only reads it once the project is **trusted** |
| `hermes` | `~/.hermes/config.yaml` | `mcp_servers:` | **YAML**, and **global** — Hermes has no project-scope file |

Two of these are not like the others, and the wizard says so on the row label and
in the summary:

- **`codex`** appends a `# BEGIN llm-wiki-base … # END llm-wiki-base` block instead
  of re-dumping the file, so your own comments and tables survive. It is only read
  after you approve the project as trusted inside Codex.
- **`hermes`** writes to your **personal** config (`~/.hermes/config.yaml`), not
  into the wiki, so it is not committed for the team and `llm-wiki-base uninstall`
  only removes it while user config is included (i.e. without `--no-user-config`).

Any file that already exists is merged, never replaced — with one exception: a
JSONC file containing comments (a hand-edited `.zed/settings.json`) is refused
rather than rewritten, because rewriting it would erase those comments. The
message prints the file to add by hand.

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
