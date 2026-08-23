"""Thin FAISS wrapper: build a flat inner-product index (cosine, since vectors
are L2-normalized), persist it + chunk metadata/text to disk, and reload it
without recomputing embeddings on every Streamlit run."""
import pickle
import faiss
import numpy as np
import config


class VectorStore:
    def __init__(self, dim: int):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.chunks = []  # list of {"text":..., **metadata}

    def add(self, vectors: np.ndarray, chunks: list[dict]):
        if vectors.ndim != 2:
            raise ValueError(f"Expected a 2-D embedding matrix, got shape {vectors.shape}.")
        if vectors.shape[0] != len(chunks):
            raise ValueError(
                f"Embedding/chunk count mismatch: {vectors.shape[0]} vectors for "
                f"{len(chunks)} chunks."
            )
        if vectors.shape[1] != self.dim:
            raise ValueError(
                f"Embedding dimension mismatch: index expects {self.dim}, "
                f"received {vectors.shape[1]}."
            )
        self.index.add(vectors.astype("float32"))
        self.chunks.extend(chunks)

    def save(self):
        config.VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(config.FAISS_INDEX_PATH))
        with open(config.METADATA_PATH, "wb") as f:
            pickle.dump(self.chunks, f)

    @classmethod
    def load(cls):
        if not config.FAISS_INDEX_PATH.exists() or not config.METADATA_PATH.exists():
            raise FileNotFoundError(
                "Vector index not found. Run `python scripts/build_index.py` first."
            )
        index = faiss.read_index(str(config.FAISS_INDEX_PATH))
        with open(config.METADATA_PATH, "rb") as f:
            chunks = pickle.load(f)
        store = cls(dim=index.d)
        store.index = index
        store.chunks = chunks
        return store

    def search(self, query_vector: np.ndarray, top_k: int = 5):
        if self.index.ntotal == 0:
            return []
        q = query_vector.astype("float32").reshape(1, -1)
        if q.shape[1] != self.dim:
            raise ValueError(
                f"Query embedding dimension {q.shape[1]} does not match "
                f"the FAISS index dimension {self.dim}. "
                "Rebuild the vector index with the same embedding model."
            )
        scores, idxs = self.index.search(q, min(top_k, self.index.ntotal))
        results = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx == -1:
                continue
            results.append({"score": float(score), **self.chunks[idx]})
        return results
