# Retrieval & eval

Union retrieval + RRF (`wiki_search` / `tools/search.py`): three independent
ranking channels fused by **reciprocal rank fusion on ranks** — never raw-score
addition, since `bm25()` and cosine live on incomparable scales.

| channel | infra | notes |
|---|---|---|
| `bm25_page` | FTS5 `pages_fts` (wiki + raw) | always on |
| `bm25_chunk` | FTS5 `chunks_fts` in `.wiki.db` | catches rare terms buried in long pages |
| `vector_chunk` | `rag/.rag_index/{chunks.json,vectors.npy}` | only when `vector = true` |

Both chunk channels **share** `tools/chunking.py`, hence identical boundaries —
if they differed, RRF between them would be meaningless. Each hit carries
`matched_by` + `rank` + `snippet` (a chunk's text: enough to **pick** a page,
not to **answer**). **Never chunked:** `index.md`/`log.md` (reserved),
translations `*.lang.md`, frontmatter, verbatim-quote footnotes.

**Rerank at the skill layer** (`[retrieval].rerank = "llm"`): the skill requests
a wide pool (`2 × top_n_final`), scores candidates by title/snippet/`matched_by`
without opening files, then opens the `top_n_final` pages. No reranker model in
code.

**Deterministic fallback, never silent:** missing model / unbuilt chunks → each
channel disables itself **and says so** (`reindex --check` reports "not built",
`eval` prints `[ERROR] channel disabled: <reason>`). Numbers that look valid
while a channel is secretly dead are a bug, not a result.

```bash
llm-wiki eval --init          # create eval/golden.toml (that's data — COMMIT it)
llm-wiki eval                 # P@k / R@k / MRR under current config
llm-wiki eval --compare       # tier1-weighted / rrf-text / rrf+vector + verdict
llm-wiki eval --compare -v    # per-query numbers
```

`eval/golden.toml` holds **real** queries + acceptable concept lists; eval warns
when a `relevant path` matches no page in the DB instead of silently scoring
wrong. Results append to `eval/results.json` (gitignored) with a config
fingerprint → comparable over time. `zero_recall_queries` = the wiki lacks
documents (an ingest job), not a bad retriever.

**Vector enablement rule:** the `+vector` profile's ΔR@k must be clearly positive
on *that wiki's own* golden set. New templates default `vector = true` on
measured evidence; old wikis stay `false` until you run `eval --compare`. At
very small scale (< ~50k tokens) BM25 is usually enough.

## The measured RRF trap

One real wiki, 18 queries / 21 pages. With equal weights, a page ranked *mid in
both* channels (consensus) can be pushed out near the cutoff by a page ranked #1
in one channel + #11 in the other — text-only RRF **lost** a query the old
weighted sum found. Three measured levers:

- `rrf_k` is **not** a lever: sweeping 20 → 250 gave identical numbers.
- `weights.bm25_page = 2.0` rescues that query (R@8 level with vector) but **MRR
  drops** below even rrf-text → use only when you refuse vector.
- `vector = true` gives both best recall and best first-hit (vector catches
  paraphrases with no shared terms — exactly where text fails): R@8
  0.9167 → **0.9722**, MRR 0.8518 → **0.8981**.

Bottom line: RRF beats weighted-sum on *coverage*, not automatically on *first
hit*. That's why the eval harness exists instead of trusting rank-fusion theory.
