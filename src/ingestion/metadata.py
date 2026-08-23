"""Assemble the metadata dict attached to every indexed chunk."""
import config


def build_chunk_metadata(filename: str, page: int, section, chunk_id: int) -> dict:
    reg = config.DOCUMENT_REGISTRY[filename]
    return {
        "source": filename,
        "document_type": reg["document_type"],
        "status": reg["status"],
        "authority": reg["authority"],
        "customer_account": reg["customer_account"],  # None = applies to all accounts
        "topic": reg["topic"],
        "page": page,
        "section": section,
        "chunk_id": chunk_id,
    }
