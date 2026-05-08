from abc import ABC, abstractmethod


class IVisionClient(ABC):
    """Abstract interface for vision/multimodal LLM operations."""

    @abstractmethod
    async def extract_findings(
        self,
        image_bytes: bytes,
        mime_type: str,
        test_type: str,
        max_retries: int = 2,
    ) -> dict:
        """Extract structured findings from an image."""
        ...

    @abstractmethod
    async def extract_tabular(
        self,
        tabular_data: dict,
        test_type: str,
    ) -> dict:
        """Extract structured findings from tabular/structured data."""
        ...
