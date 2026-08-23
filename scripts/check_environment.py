"""Quick ParcelPilot environment/index consistency check."""
import json
from pathlib import Path
import config

def main():
    print("GEMINI_API_KEY configured:", bool(config.GEMINI_API_KEY))
    print("FAISS index:", config.FAISS_INDEX_PATH.exists())
    print("Metadata:", config.METADATA_PATH.exists())
    print("Embedder marker:", config.EMBEDDER_INFO_PATH.exists())
    if config.EMBEDDER_INFO_PATH.exists():
        print("Embedder:", json.loads(config.EMBEDDER_INFO_PATH.read_text())["name"])
    fallback = config.VECTORSTORE_DIR / "fallback_vectorizer.pkl"
    print("Stale fallback present:", fallback.exists())
    print("\nIf the marker says sentence_transformers_minilm, query-time retrieval will use MiniLM.")
    print("If it says tfidf_fallback, the persisted TF-IDF vectorizer will be used.")
if __name__ == "__main__":
    main()
