"""
Async RAG retriever for the AI Service.

Embeds the query via Ollama (nomic-embed-text) then performs a vector
search in Qdrant (REST API), with an optional department filter.

Usage:
    retriever = QdrantRetriever()
    context_str = await retriever.get_context("chest pain shortness of breath",
                                               department="cardiology")
"""

import logging
from typing import Optional

import httpx

from Domain.interfaces import IRetriever
from infrastructure.config import get_settings

logger = logging.getLogger(__name__)


class QdrantRetriever(IRetriever):
    """
    Async wrapper around Qdrant REST API + Ollama for knowledge-base retrieval.

    Instantiated once per process and shared across requests.
    Falls back to empty context on any error so upstream pipelines are
    never hard-blocked by a RAG outage.
    """

    def __init__(self) -> None:
        s = get_settings()
        self._enabled    = s.RAG_ENABLED
        self._collection = s.QDRANT_COLLECTION
        self._ollama_url = s.OLLAMA_URL.rstrip("/")
        self._qdrant_url = s.QDRANT_URL.rstrip("/")

    # ── Public API -------------------------------------------------------

    async def get_context(
        self,
        query:      str,
        department: Optional[str] = None,
        top_k:      int = 3,
    ) -> str:
        """
        Returns a formatted knowledge-base context block ready for prompt
        injection.  Returns an empty string when RAG is disabled or fails.
        """
        if not self._enabled:
            return ""

        try:
            vector = await self._embed(query)
            hits   = await self._search(vector, department, top_k)
            return self._format(hits)
        except Exception as exc:
            logger.warning("RAG retrieval failed (query=%r): %s", query[:60], exc)
            return ""

    # ── Internal ---------------------------------------------------------

    async def _embed(self, text: str) -> list[float]:
        """Call Ollama /api/embed with model and list input, return first embedding."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._ollama_url}/api/embed",
                json={"model": "nomic-embed-text", "input": [text]},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"][0]

    async def _search(
        self,
        vector:     list[float],
        department: Optional[str],
        top_k:      int,
    ) -> list[dict]:
        """Qdrant vector search via REST API (compatible with Qdrant 1.9.x)."""
        filter_body: Optional[dict] = None
        if department:
            filter_body = {
                "must": [
                    {
                        "key": "department",
                        "match": {"value": department}
                    }
                ]
            }

        payload = {
            "vector": vector,
            "limit": top_k,
            "with_payload": True,
        }
        if filter_body:
            payload["filter"] = filter_body

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._qdrant_url}/collections/{self._collection}/points/search",
                json=payload,
            )
            resp.raise_for_status()
            results = resp.json()

        hits = results.get("result", [])
        return [
            {
                "text":    (hit.get("payload") or {}).get("text", ""),
                "source":  (hit.get("payload") or {}).get("source_url", "")
                           or (hit.get("payload") or {}).get("source", ""),
                "section": (hit.get("payload") or {}).get("section_heading", ""),
                "score":   hit.get("score", 0.0),
            }
            for hit in hits
        ]

    @staticmethod
    def _format(hits: list[dict]) -> str:
        """Format retrieved chunks into a single context block for the prompt."""
        if not hits:
            return ""
        lines = ["── KNOWLEDGE BASE CONTEXT (from verified medical guidelines) ──"]
        for i, h in enumerate(hits, 1):
            section = f" › {h['section']}" if h.get("section") else ""
            lines.append(f"\n[{i}] {h.get('source', '')}{section}")
            lines.append(h["text"].strip())
        lines.append("── END CONTEXT ──")
        return "\n".join(lines)
