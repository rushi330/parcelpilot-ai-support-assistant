"""Build (or rebuild) the FAISS vector index from the PDF knowledge base.

Run: python scripts/build_index.py

Pipeline: discover -> load/extract -> clean -> chunk -> metadata -> embed ->
normalize -> FAISS -> persist (index.faiss + metadata.pkl).

Deprecated documents (active_for_retrieval=False in config.DOCUMENT_REGISTRY)
are intentionally EXCLUDED from the index so they can never surface as
current-policy evidence.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src.ingestion.document_loader import discover_documents, load_document_pages
from src.ingestion.chunker import chunk_page
from src.ingestion.metadata import build_chunk_metadata
from src.embeddings.embedder import embed_corpus
from src.retrieval.vector_store import VectorStore


def main():
    print("Discovering documents in", config.KNOWLEDGE_BASE_DIR)
    all_pdfs = discover_documents()
    print(f"Found {len(all_pdfs)} classified PDF(s).")

    all_chunk_texts = []
    all_chunk_meta = []
    chunk_counter = 0

    for pdf_path in all_pdfs:
        reg = config.DOCUMENT_REGISTRY[pdf_path.name]
        if not reg["active_for_retrieval"]:
            print(f"  SKIP (excluded from active index, status={reg['status']}): {pdf_path.name}")
            continue

        print(f"  Ingesting: {pdf_path.name} (status={reg['status']}, authority={reg['authority']})")
        pages = load_document_pages(pdf_path)
        for page_num, page_text in pages:
            for chunk in chunk_page(page_text):
                meta = build_chunk_metadata(pdf_path.name, page_num, chunk["section"], chunk_counter)
                all_chunk_texts.append(chunk["text"])
                all_chunk_meta.append({**meta, "text": chunk["text"]})
                chunk_counter += 1

    if not all_chunk_texts:
        print("ERROR: no chunks produced. Aborting.")
        sys.exit(1)

    print(f"\nTotal chunks: {len(all_chunk_texts)}")
    print("Generating embeddings (local)...")
    vectors, embedder_name = embed_corpus(all_chunk_texts)
    print(f"Embedder used: {embedder_name}")
    if embedder_name == "sentence_transformers_minilm":
        fallback_path = config.VECTORSTORE_DIR / "fallback_vectorizer.pkl"
        if fallback_path.exists():
            fallback_path.unlink()
            print("Removed stale fallback_vectorizer.pkl because this index uses MiniLM.")
    print("Embedding shape:", vectors.shape)

    store = VectorStore(dim=vectors.shape[1])
    store.add(vectors, all_chunk_meta)
    store.save()
    print(f"\nSaved index to {config.FAISS_INDEX_PATH}")
    print(f"Saved metadata to {config.METADATA_PATH}")
    print(f"Index contains {store.index.ntotal} vectors.")


if __name__ == "__main__":
    main()
