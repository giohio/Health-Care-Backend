"""
Query-time retrieval with mandatory department filter.
Uses small-to-big retrieval: fetches child chunks, then expands to parent
context before returning results to the AI service.
"""

from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

from pipeline.embedder import embed_single
from pipeline.qdrant_loader import COLLECTION_NAME, get_client


def retrieve(
    query:            str,
    department:       str,
    top_k:            int = 5,
    chunk_types:      Optional[List[str]] = None,
    disease_category: Optional[str] = None,
) -> List[dict]:
    """
    Main retrieval function called by the AI service.

    Returns a list of dicts:
        {"text", "score", "source", "page", "section", "dept", "type"}

    IMPORTANT — department filter is mandatory.
    Without it, cardiology content will surface in respiratory queries.
    """
    client    = get_client()
    query_vec = embed_single(query)

    # Build Qdrant filter
    must: List[FieldCondition] = [
        FieldCondition(key="department", match=MatchValue(value=department))
    ]

    if chunk_types:
        must.append(
            FieldCondition(key="chunk_type", match=MatchAny(any=chunk_types))
        )

    if disease_category:
        must.append(
            FieldCondition(
                key="disease_category",
                match=MatchValue(value=disease_category),
            )
        )

    hits = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vec.tolist(),
        query_filter=Filter(must=must),
        limit=top_k,
        with_payload=True,
    )

    results: List[dict] = []
    for hit in hits:
        payload = hit.payload or {}
        text    = payload.get("text", "")

        # Small-to-big: if this chunk is a child, prepend the parent text
        if payload.get("chunk_type") == "child" and payload.get("parent_id"):
            parent = _fetch_by_uint_id(client, payload["parent_id"])
            if parent:
                parent_text = (parent.payload or {}).get("text", "")
                text = parent_text + "\n\n[Excerpt]\n" + text

        results.append(
            {
                "text":    text,
                "score":   hit.score,
                "source":  payload.get("source"),
                "page":    payload.get("page_title"),
                "section": payload.get("section_heading"),
                "dept":    payload.get("department"),
                "type":    payload.get("chunk_type"),
            }
        )

    return results


def _fetch_by_uint_id(client: QdrantClient, chunk_id_hex: str):
    """
    Fetch a single point by its hex chunk_id (converted to uint64).
    Used to retrieve a parent chunk for small-to-big context expansion.
    """
    try:
        point_id = int(chunk_id_hex, 16)
        hits = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[point_id],
            with_payload=True,
        )
        return hits[0] if hits else None
    except Exception:
        return None
