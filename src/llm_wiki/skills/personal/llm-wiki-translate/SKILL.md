---
name: llm-wiki-translate
description: Translate 1 hoặc nhiều wiki page sang target language đã setup. Dùng LLM của AI tool đang chạy (Claude Code → Claude, OpenCode → provider). Bản dịch là file song song <slug>.<lang>.md, KHÔNG vào DB/RAG. Dùng khi user bảo "dịch page X sang tiếng Việt" hoặc sau ingest có target lang enabled.
---

# llm-wiki Translate

Wiki song ngữ: mỗi source page `wiki/<domain>/<kind>/<slug>.md` có thể có bản dịch song song `wiki/<domain>/<kind>/<slug>.<lang>.md`. Bản dịch:
- Cùng frontmatter keys với source (`title`, `domain`, `kind`, `sources`, `updated`, `status`).
- Body dịch 100% tương đương — không thêm, không bớt, không paraphrase.
- **KHÔNG vào DB/RAG** (skip rule `*.lang.md` ở `tools/{ingest,reindex,watch}.py` + `rag/index.py`).

## LLM provider

**Dùng LLM của AI tool đang chạy** — KHÔNG gọi API riêng:
- Claude Code → Claude (claude-sonnet-4-5 hoặc model hiện tại của session).
- OpenCode → provider đang config trong `opencode.json`.
- Zed → provider đang config.

Env `LLM_WIKI_TRANSLATE_API_KEY` / `LLM_WIKI_TRANSLATE_BASE_URL` / `LLM_WIKI_TRANSLATE_MODEL` là **OPTIONAL bypass** — chỉ dùng nếu user muốn gọi OpenAI API riêng thay vì AI tool LLM. Mặc định bỏ qua.

## Khi nào dùng

- User bảo "dịch trang X sang tiếng N".
- Sau khi ingest 1 source mới, nếu `.llm-wiki.toml` có `[translate].enabled = true` → ingest skill tự invoke skill này cho mỗi target lang.
- Re-translate khi source update: chạy `llm-wiki translate check --lang <code>` để phát hiện drift, rồi gọi skill này lại cho các file mismatch.

## Workflow

### 1. Xác định target langs

Đọc `.llm-wiki.toml` ở wiki root:

```toml
[translate]
enabled = true
langs = ["vi", "ja"]
```

Nếu user request lang cụ thể → dùng lang đó, ignore config. Nếu không có target langs trong config VÀ user không chỉ định → hỏi user.

### 2. Với mỗi (source page, target lang) cần dịch

**Bước a**: Đọc source page `wiki/<domain>/<kind>/<slug>.md`.

**Bước b**: Tách frontmatter (giữa 2 line `---`) + body.

**Bước c**: Gọi LLM của AI tool hiện tại để dịch body. Prompt chuẩn:

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

**Bước d**: Ghép lại với frontmatter gốc (verbatim — bản dịch có CÙNG `sources`, `kind`, `updated` để provenance intact). Output: file hoàn chỉnh.

**Bước e**: Ghi file `wiki/<domain>/<kind>/<slug>.<lang>.md`.

**Bước f** (verify nhanh): kiểm tra heading count khớp source. Nếu lệch → retry 1 lần với prompt stricter: "Your previous translation added/removed headings. Try again, output EXACTLY the same heading structure as input."

### 3. Sau khi dịch xong tất cả

Chạy:

```bash
llm-wiki translate check --lang <code>
```

Nếu mismatch → flag cho user, không tự fix. Lý do mismatch phổ biến: LLM paraphrase, LLM thêm/bớt heading, source vừa update sau khi dịch.

## Ingest integration

Khi ingest skill viết 1 source mới, nếu `.llm-wiki.toml` có `[translate].enabled = true`:
1. Ingest viết source EN → `wiki/<domain>/source/<slug>.md` (như cũ).
2. Với mỗi lang trong `langs`: invoke workflow trên để tạo `<slug>.<lang>.md`.
3. Sau ingest xong, reindex — bản dịch tự skip khỏi DB.

**Cost note**: ingest N sources × M langs = N×M LLM calls. Cảnh báo user nếu:
- `len(langs) > 5` → "5+ target langs, tốn token. Confirm continue?"
- `N sources > 20` → "20+ sources, suggest ingest theo batch."

## Constraints

- **Không dịch code block, URL, technical term** (class name, function name, package name, version number, command flag, env var).
- **Không paraphrase** — chỉ dịch text tự nhiên. Markdown structure phải preserved 100%.
- **Không thêm ý kiến** — nếu source ngắn gọn, bản dịch cũng ngắn gọn tương đương.
- **Frontmatter verbatim** — `sources` (provenance), `updated`, `status` KHÔNG đổi.
- **Heading structure preserved** — số heading + levels + text phải khớp source (check bằng `llm-wiki translate check`).
- **Wikilinks preserved** — `[[wiki/<domain>/...]]` giữ nguyên path, KHÔNG dịch alias text thành localized version (để Obsidian resolve đúng path).
- **Code blocks** — giữ nguyên 100% (không dịch comments trong code).

## An toàn

- Bản dịch là file parallel, không sửa source.
- Nếu LLM trả output malformed (thiếu markdown, thêm preamble/suffix) → retry 1 lần với prompt stricter. Nếu vẫn fail → flag cho user, skip file đó, KHÔNG ghi file rỗng.
- Nếu user không setup target langs (`enabled = false` hoặc file không tồn tại) VÀ không chỉ định lang trong request → KHÔNG dịch, KHÔNG hỏi thêm (im lặng skip). Trừ khi user explicit "dịch sang tiếng X".
- Cross-wiki contamination: nếu đang ở project wiki khác (multi-project), check `<wiki-root>/.llm-wiki.toml` của project hiện tại, KHÔNG dùng config từ project khác.
