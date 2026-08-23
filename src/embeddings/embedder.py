"""Local embedding generation with persisted embedder identity.

The vector index and the query encoder MUST use the same embedding model.
Older versions of this project selected the TF-IDF fallback merely because
``fallback_vectorizer.pkl`` existed. That was unsafe: after rebuilding the
index with MiniLM, a stale fallback file could still be present, producing a
query vector with the wrong dimension and causing FAISS to raise an
AssertionError.

This version persists the actual embedder used for the index in
``vectorstore/embedder.json`` and uses that marker at query time.
"""
from functools import lru_cache
import json
import pickle
import numpy as np
import config

_FALLBACK_PATH = config.VECTORSTORE_DIR / "fallback_vectorizer.pkl"


class _TfidfEmbedder:
    name = "tfidf_fallback"

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vectorizer = TfidfVectorizer(max_features=512)
        self._fitted = False

    def fit(self, texts: list[str]):
        self.vectorizer.fit(texts)
        self._fitted = True

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError(
                "TF-IDF fallback vectorizer is not fitted. Rebuild the vector index."
            )
        return self.vectorizer.transform(texts).toarray().astype("float32")

    def save(self):
        config.VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_FALLBACK_PATH, "wb") as f:
            pickle.dump(self.vectorizer, f)

    @classmethod
    def load(cls):
        if not _FALLBACK_PATH.exists():
            raise FileNotFoundError(
                "The index was built with TF-IDF, but fallback_vectorizer.pkl is missing. "
                "Run `python scripts/build_index.py`."
            )
        obj = cls.__new__(cls)
        with open(_FALLBACK_PATH, "rb") as f:
            obj.vectorizer = pickle.load(f)
        obj._fitted = True
        return obj


class _SentenceTransformerEmbedder:
    name = "sentence_transformers_minilm"

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(config.EMBEDDING_MODEL)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(
            texts, show_progress_bar=False, convert_to_numpy=True
        )


def _save_embedder_info(name: str):
    config.VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.EMBEDDER_INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"name": name, "model": config.EMBEDDING_MODEL if name == "sentence_transformers_minilm" else None},
            f,
            indent=2,
        )


def _load_embedder_name() -> str | None:
    if not config.EMBEDDER_INFO_PATH.exists():
        return None
    try:
        with open(config.EMBEDDER_INFO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("name")
    except (OSError, ValueError, TypeError):
        return None


@lru_cache(maxsize=1)
def _get_active_embedder(for_query_reload: bool = False):
    """Return the exact encoder used to build the persisted index.

    For a new index build, prefer MiniLM and fall back to TF-IDF only if the
    model cannot be loaded.

    For query time, use the persisted embedder marker. If the marker is
    missing (legacy project), default to MiniLM rather than blindly selecting
    TF-IDF from the mere presence of a stale fallback file. This matches the
    supplied project's current 384-dimensional MiniLM index.
    """
    if for_query_reload:
        name = _load_embedder_name()
        if name == "tfidf_fallback":
            return _TfidfEmbedder.load()
        if name == "sentence_transformers_minilm":
            return _SentenceTransformerEmbedder()

        # Legacy index with no marker: prefer the configured MiniLM model.
        # A user can run build_index.py to create the marker permanently.
        try:
            return _SentenceTransformerEmbedder()
        except Exception:
            if _FALLBACK_PATH.exists():
                return _TfidfEmbedder.load()
            raise

    try:
        return _SentenceTransformerEmbedder()
    except Exception as e:
        print(
            f"[embedder] sentence-transformers unavailable ({type(e).__name__}); "
            "falling back to local TF-IDF embedder for this environment."
        )
        return _TfidfEmbedder()


def embed_corpus(texts: list[str]) -> tuple[np.ndarray, str]:
    """Build-time encoding. Persists the encoder identity."""
    embedder = _get_active_embedder(for_query_reload=False)
    if isinstance(embedder, _TfidfEmbedder):
        embedder.fit(texts)
        embedder.save()
    vecs = embedder.encode(texts)
    vecs = _normalize(vecs)
    _save_embedder_info(embedder.name)
    return vecs, embedder.name


def embed_query(text: str) -> np.ndarray:
    """Query-time encoding using the same encoder as the persisted index."""
    embedder = _get_active_embedder(for_query_reload=True)
    vecs = embedder.encode([text])
    return _normalize(vecs)[0]


def _normalize(vecs: np.ndarray) -> np.ndarray:
    vecs = np.asarray(vecs, dtype="float32")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1e-8
    return vecs / norms
