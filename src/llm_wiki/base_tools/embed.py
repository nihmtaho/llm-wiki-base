import os

EMBED_DIM = int(os.environ.get("WIKI_EMBED_DIM", "384"))
DEFAULT_MODEL = os.environ.get("WIKI_EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")


class EmbedProvider:
    """On-device embedding chỉ qua fastembed. Không dùng API."""

    def __init__(self, model=None):
        self.model = model or DEFAULT_MODEL
        self._fe = None

    def embed(self, texts):
        if self._fe is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as e:
                raise RuntimeError("fastembed chưa cài: pip install fastembed") from e
            self._fe = TextEmbedding(self.model)
        vecs = list(self._fe.embed(texts, normalize=True))
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vecs]
