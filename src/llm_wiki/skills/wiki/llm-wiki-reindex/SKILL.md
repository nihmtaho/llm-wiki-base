---
name: llm-wiki-reindex
description: >
  Dựng / làm mới chỉ mục search DERIVED từ markdown: BM25 page + BM25 chunk + (tuỳ chọn)
  vector chunk. Tăng dần theo content-hash; có dry-run và full rebuild. Dùng khi ingest
  xong, khi lint báo lệch index, hoặc sau khi đổi config retrieval. KHÔNG bao giờ commit
  chỉ mục.
---

# LLM Wiki — Reindex

Markdown là nguồn sự thật; chỉ mục là **derived** — vứt đi rebuild được. Skill này chỉ lo một việc: làm cho chỉ mục khớp markdown và khớp config.

## Có gì trên đĩa

| thành phần | nơi nằm | dựng khi |
|---|---|---|
| `pages_fts` (BM25 page) | `wiki/.wiki.db` | luôn |
| `chunks_fts` (BM25 chunk) | `wiki/.wiki.db` | **luôn** — không phụ thuộc `vector` |
| vector chunk (`.json` + `.npy`) | `rag/.rag_index/` | chỉ khi `[retrieval].vector = true` |

Hai kênh chunk dùng **chung** `tools/chunking.py` → cùng ranh giới, nên RRF giữa chúng có nghĩa.

**Không được index:** `wiki/index.md` + `wiki/log.md` (reserved), bản dịch `*.<lang>.md`, frontmatter, footnote verbatim (bằng chứng nguyên văn — vào index thì mọi query từ khoá đều ăn điểm giả).

## Chế độ

```bash
llm-wiki reindex            # tăng dần (mặc định): chỉ file mới/đổi/xoá theo content-hash
llm-wiki reindex --check    # dry-run: báo sẽ index gì, sẽ xoá gì, config drift, trạng thái chunk index
llm-wiki reindex --full     # rebuild toàn bộ — BẮT BUỘC sau khi đổi chunk_tokens / embed_model / vector / fusion
```

Chạy từ trong `<wiki_root>`. `watch` daemon tự reindex theo mtime mỗi `WATCH_REINDEX_SEC` — nên skill này chỉ cần khi bạn muốn kết quả **ngay** hoặc muốn debug.

## Quy trình

1. **Xem trạng thái trước** (không ghi gì): `llm-wiki reindex --check`. Đọc:
   - số file sẽ index / sẽ xoá;
   - **config drift** — nếu in ra cảnh báo "config đổi so với lần reindex trước" → bạn phải `--full`, không phải incremental;
   - **chunk index** — "chưa build" nghĩa là kênh `bm25_chunk` đang chết, search chỉ có 2 kênh.
2. **Chạy đúng chế độ**:
   - Không đổi config → `llm-wiki reindex`.
   - Đổi `chunk_tokens` / `embed_model` / `vector` / `fusion` / `chunk_bm25` → `llm-wiki reindex --full`. Lý do phải full: incremental bỏ qua page có content-hash không đổi, nên wiki cũ sẽ **không bao giờ** có chunk nếu không force.
   - Lần đầu sau khi nâng cấp `llm-wiki base install` mà `SCHEMA_VERSION` tăng → `--full` (đây là lý do bump version, không phải trang trí).
3. **Xác nhận bằng số**, không bằng cảm giác:
   ```bash
   llm-wiki config show          # giá trị THỰC (đã áp env override, có nhãn [env]/[toml]/[default])
   llm-wiki reindex --check      # phải báo 0 file pending + không drift
   ```
   Số chunk của `chunks_fts` phải **bằng** số chunk trong `rag/.rag_index/chunks.json` khi `vector = true` — lệch nhau nghĩa là 2 kênh không cùng ranh giới (bug, không phải cấu hình).
4. **Kiểm kênh chết**: `llm-wiki eval` (nếu có `eval/golden.toml`) in `[ERROR] kênh bị tắt vì lỗi` — phân biệt "tắt vì config" với "tắt vì hỏng".
5. Báo cáo: N page indexed, chunk +/−, vector on/off, có drift không.

## Quan hệ với skill khác

- `llm-wiki-ingest` / `llm-wiki-consolidate` gọi reindex **tăng dần** cho phần vừa đổi — đó là bước cuối của chúng.
- `llm-wiki-lint` chỉ *phát hiện* index lệch; `reindex` *sửa*.
- Đổi `chunk_tokens`/`embed_model`/bật-tắt `vector` ⇒ `--full`, rồi **đo lại** bằng `llm-wiki eval --compare` (số liệu cũ không còn so sánh được — fingerprint khác).

## Không làm

- Không commit chỉ mục: `.wiki.db`, `rag/.rag_index/`, `.env` đã nằm trong `.gitignore` của wiki. Đừng `git add -f`.
- Không sửa markdown khi reindex — chỉ mục là một chiều (md → index).
- Không coi chỉ mục là nguồn sự thật: nếu index và markdown khác nhau, **markdown đúng**.
- Không rebuild `--full` "cho chắc" khi chưa đổi config — với `vector = true` nó re-embed toàn bộ (chi phí model + GPU/CPU), và xoá lịch sử so sánh được nếu fingerprint đổi.
