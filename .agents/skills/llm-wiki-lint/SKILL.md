---
name: llm-wiki-lint
description: Health-check LLM wiki — tìm orphan page, broken link, missing index entry, frontmatter thiếu domain/kind, stale claim. Contradiction báo human. Dùng định kỳ hoặc khi human yêu cầu.
---

# LLM Wiki — Lint

Schema: `_schema.md`. Runbook: `CLAUDE.md`.

## Khi nào
Định kỳ (watch chạy mỗi `WATCH_LINT_SEC`) hoặc human bảo "lint wiki".

## Quy trình
1. Chạy `wiki_lint()` → trả `page_count`, `orphans`, `missing_file`, `findings`.
   - Hoặc CLI: `PYTHONPATH=tools .venv/bin/python -c "import db,lint; print(lint.lint(db.get_conn()))"`.
2. Xử lý:
   - **orphan** (page không có inbound `[[link]]`): tìm page liên quan để link tới, hoặc ghi nhận intentional.
   - **missing_file**: page trong DB nhưng thiếu file trên disk → reconcile.
   - **broken link**: `[[target]]` trỏ sai path → sửa.
   - **missing index entry**: page chưa có trong `wiki/<domain>/index.md` hoặc domain mới chưa có row trong `wiki/index.md` → thêm.
   - **frontmatter thiếu `domain`/`kind`**: page cũ chỉ có `category: <folder>`. Khi sửa, bổ sung `domain` + `kind` mới (infer từ path hoặc detect đúng).
   - **`sources:` chứa local path** (rule `sources-no-local-path`): drop path, đặt `[]` hoặc chỉ giữ URL.
   - **Body inline `[[raw/...]]` / `[[archived/...]]`** (rule `body-no-raw-archived-wikilink`): xoá hoặc chuyển vào `sources:`.
3. **Sync index (DB + rag)** — đảm bảo search DB (`wiki/.wiki.db`) và rag (`rag/.rag_index/`) đồng bộ với wiki:
   - Check: `PYTHONPATH=tools .venv/bin/python -c "import os,glob,db; c=db.get_conn(); db.init_db(c); w=[os.path.relpath(f,db.WIKI_ROOT) for f in glob.glob(os.path.join(db.WIKI_ROOT,'wiki','**','*.md'),recursive=True) if not os.path.basename(f).startswith('.')]; p=set(x['path'] for x in db.list_pages(c)); print('wiki_files',len(w),'db_pages',len(p),'missing_in_db',[x for x in w if x not in p]); print('rag_index_exists',os.path.exists(os.path.join(db.WIKI_ROOT,'rag','.rag_index','vectors.npy')))"`
   - Nếu `missing_in_db` không rỗng, hoặc rag index thiếu/stale (mtime cũ hơn wiki mới nhất) → chạy `.venv/bin/python tools/reindex.py` (index `raw/**`+`wiki/**` vào DB + rebuild rag, idempotent).
4. **Contradiction** (2 page claim mâu thuẫn): đọc kỹ, **report human** kèm trích dẫn. Không materialize thành edge trên lời model.
5. **Stale claim**: source mới hơn đã supersede → đánh dấu `status: stale` + `confidence: superseded`, đề xuất update.
6. **Domain coverage**: liệt kê tất cả top-level folder `wiki/*/` (không tính `index.md`, `log.md`, `.proposals/`). Mỗi folder nên có `index.md`. Nếu folder không có `index.md` hoặc có nhưng rỗng → tạo/cập nhật.

## MCP tools
- `wiki_lint` · `wiki_list` · `wiki_read`.

## An toàn
- Lint chỉ báo cáo. Sửa cross-link/index/frontmatter là re-derivable → agent tự làm.
- Quyết định semantic (contradiction, stale) thuộc human.
- Không xoá page kể cả khi orphan — người quyết định.
