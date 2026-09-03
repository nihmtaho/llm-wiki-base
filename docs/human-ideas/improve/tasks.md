**1. Skills — gom + phân phối** (theo `docs/human-ideas/my-idea/skill-idea`)
- Gom skills riêng lẻ (personal-wiki + project-wiki) → 6 skills: ingest, query, lint, reindex, review, consolidate, research
- Phân biệt rõ: `query` = research trong wiki hiện tại; `research` = research knowledge trong các wiki chỉ định
- Skill `research` cài vào root_codebase (`root_project/.agents/skills/`), không phải `root_project/wiki/.agents/skills/`
- Khi init: symlink `research` cho các agents khác (claude, opencode với `commands/`) —复用 `src/llm_wiki/base_scripts/link_skills.sh`

**2. CLI + MCP**
- MCP per-wiki với CLI khi init, support claude, opencode, commandcode:
  - claude: [Claude MCP Docs](https://code.claude.com/docs/en/mcp)
  - opencode: [OpenCode MCP Docs](https://opencode.ai/docs/mcp-servers/)
  - commandcode: [CommandCode MCP Docs](https://commandcode.ai/docs/mcp)
- MCP init: chỉ rõ vị trí cài đặt khi user chọn yes (global: user scope, hay project/personal wiki: root_project scope)
- Cleanup CLI: CLI cần LLM không chạy độc lập được → báo lỗi rõ, hướng dẫn cài providers hoặc chạy qua agent tool

**3. Config + đặt tên wiki**
- Đổi cách đặt tên wiki: user-name + UUID
- Config thêm providers cho wiki → ingest không cần mở agent tool (claude code / opencode)
- Bật vector mặc định khi init
- Tối ưu config mặc định: `chunk_tokens, top_k_bm25, top_k_vector, top_n_final, bm25_weight, vec_weight`
- Thêm ngôn ngữ mặc định của wiki vào `.llm-wiki.toml`, llm khi ingest tạo wiki thì sẽ dựa theo ngôn ngữ này.

**4. Cleanup**
- Kiểm tra `.proposals`, dư thừa thì xoá
