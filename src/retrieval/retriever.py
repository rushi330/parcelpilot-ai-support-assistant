"""Query-time retrieval: embed query -> FAISS search -> metadata filtering
(customer_account scoping + status filtering) -> lightweight keyword/entity
boost -> ranked evidence.

Deprecated documents are already excluded at index-build time, but we keep an
explicit status filter here too as defense in depth.
"""
import re
from functools import lru_cache
import config
from src.embeddings.embedder import embed_query
from src.retrieval.vector_store import VectorStore

# Entity-like tokens worth exact-matching regardless of embedding quality:
# known-issue IDs, order/ticket/account IDs, and carrier/product proper nouns.
_ENTITY_RE = re.compile(r"\b(KI-\d+|ORD-\d+|TKT-\d+|ACCT-\d+|SwiftShip|BlueDart(?: Pro)?|RoadRunner|BOOKED|PICKED_UP|DELIVERED)\b", re.IGNORECASE)
_KEYWORD_BOOST = 0.15


@lru_cache(maxsize=1)
def _get_store():
    return VectorStore.load()


def _extract_entities(text: str) -> set[str]:
    return {m.group(0).upper() for m in _ENTITY_RE.finditer(text)}


def search_documents(query: str, account_id: str = None, topic: str = None, top_k: int = None) -> list[dict]:
    """Search the active knowledge base.

    Returns chunks visible to `account_id`: i.e. chunks with
    customer_account == None (general docs) OR customer_account == account_id
    (that customer's own agreement). Another customer's agreement is never
    returned, even if it scores well.
    """
    top_k = top_k or config.TOP_K
    store = _get_store()
    qvec = embed_query(query)
    # Over-fetch then filter, since account/topic filtering happens post-search
    raw_results = store.search(qvec, top_k=max(top_k * 4, 10))

    query_entities = _extract_entities(query)

    filtered = []
    for r in raw_results:
        if r.get("status") == "deprecated":
            continue
        chunk_account = r.get("customer_account")
        if chunk_account is not None and chunk_account != account_id:
            continue  # another customer's agreement - never expose
        if topic and r.get("topic") != topic:
            continue
        # Hybrid boost: exact entity overlap between query and chunk text
        # nudges ranking without making retrieval solely dependent on
        # embedding-similarity quality.
        if query_entities:
            chunk_entities = _extract_entities(r["text"])
            overlap = len(query_entities & chunk_entities)
            r = {**r, "score": r["score"] + overlap * _KEYWORD_BOOST}
        filtered.append(r)

    filtered.sort(key=lambda r: r["score"], reverse=True)
    return filtered[:top_k]
