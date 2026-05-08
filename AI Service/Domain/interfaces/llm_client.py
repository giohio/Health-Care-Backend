from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Callable, Optional


class ILLMClient(ABC):
    """Abstract interface for text LLM operations."""

    @abstractmethod
    async def stream_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]: ...

    @abstractmethod
    async def stream_conversation(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]: ...

    @abstractmethod
    async def stream_with_tools(
        self,
        messages:     list[dict],
        tools:       Optional[list[dict]] = None,
        tool_handler: Optional[Callable[[str, dict], Any]] = None,
        temperature: float = 0.6,
        max_tokens:  int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Streaming completion with tool-calling support.

        Args:
            messages: Full conversation list (system + history + current turn).
            tools: List of tool definitions.
            tool_handler: Callable(tool_name, args) -> dict; handles tool executions.
            temperature, max_tokens: LLM parameters.
        """
        ...

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        """Non-streaming completion.

        Args:
            json_mode: When True, returns raw text without an AI disclaimer
                       appended — used for structured/JSON output.
        """
        ...

    @abstractmethod
    async def complete_structured(
        self,
        system_prompt:   str,
        user_prompt:     str,
        response_schema: dict,
        temperature:     float = 0.2,
        max_tokens:      int   = 512,
        max_retries:     int   = 3,
    ) -> dict:
        """Constrained JSON completion using a schema.

        Args:
            response_schema: JSON Schema dict the model must conform to.
            max_retries: How many times to retry on rate-limit errors.
        """
        ...
