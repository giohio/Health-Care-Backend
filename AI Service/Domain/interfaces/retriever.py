from abc import ABC, abstractmethod
from typing import Optional


class IRetriever(ABC):
    """Abstract interface for RAG knowledge-base retrieval."""

    @abstractmethod
    async def get_context(
        self,
        query: str,
        department: Optional[str] = None,
        top_k: int = 3,
    ) -> str:
        """Return a formatted knowledge-base context block for prompt injection."""
        ...
