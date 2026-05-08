"""
Unit tests for infrastructure/llm/groq_client.py

Uses Fake objects injected directly into GroqClient internals to avoid
real API calls. All tests are sync/async without hitting the network.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from infrastructure.llm.groq_client import GroqClient
from Domain.prompts import AI_DISCLAIMER_VI


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------

class FakeStreamChunk:
    """Mimics a single token chunk returned by groq stream."""
    def __init__(self, content):
        self.choices = [MagicMock(delta=MagicMock(content=content))]


class FakeAsyncStream:
    """Async iterator that yields pre-defined chunks."""
    def __init__(self, chunks):
        self._iter = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class FakeCompletions:
    """Fake chat.completions object supporting both stream and non-stream."""

    def __init__(self, stream_chunks=None, complete_text="", raise_error=False):
        self._stream_chunks = stream_chunks or []
        self._complete_text = complete_text
        self._raise_error = raise_error

    async def create(self, **kwargs):
        await asyncio.sleep(0)
        if self._raise_error:
            raise RuntimeError("Groq API unavailable")
        if kwargs.get("stream"):
            return FakeAsyncStream(self._stream_chunks)
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content=self._complete_text))]
        return resp


def _make_groq_client(stream_chunks=None, complete_text="", raise_error=False) -> GroqClient:
    """Build a GroqClient wired to Fake internals (no real API key needed)."""
    client = object.__new__(GroqClient)
    fake_completions = FakeCompletions(stream_chunks, complete_text, raise_error)
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_groq = MagicMock()
    fake_groq.chat = fake_chat
    client._client = fake_groq
    client._model = "llama-3.3-70b-versatile"
    client._timeout = 60
    return client


# ---------------------------------------------------------------------------
# stream_completion tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_completion_yields_all_chunks():
    chunks = [FakeStreamChunk("Xin"), FakeStreamChunk(" chào"), FakeStreamChunk("!")]
    client = _make_groq_client(stream_chunks=chunks)

    result = []
    async for token in client.stream_completion("system", "Xin chào bạn"):
        result.append(token)

    assert result == ["Xin", " chào", "!",  f"\n\n{AI_DISCLAIMER_VI}"]


@pytest.mark.asyncio
async def test_stream_completion_skips_none_deltas():
    chunks = [
        FakeStreamChunk("Hello"),
        FakeStreamChunk(None),   # None delta should be skipped
        FakeStreamChunk(" world"),
    ]
    client = _make_groq_client(stream_chunks=chunks)

    result = []
    async for token in client.stream_completion("system", "user"):
        result.append(token)

    assert "Hello" in result
    assert " world" in result
    assert None not in result


@pytest.mark.asyncio
async def test_stream_completion_appends_disclaimer():
    client = _make_groq_client(stream_chunks=[FakeStreamChunk("Kết quả.")])

    last_chunk = None
    async for token in client.stream_completion("system", "Kết quả xét nghiệm"):
        last_chunk = token

    assert AI_DISCLAIMER_VI in last_chunk


@pytest.mark.asyncio
async def test_stream_completion_error_yields_error_message():
    client = _make_groq_client(raise_error=True)

    result = []
    async for token in client.stream_completion("system", "Xét nghiệm máu"):
        result.append(token)

    assert len(result) == 1
    assert "[LỖI]" in result[0]


# ---------------------------------------------------------------------------
# complete tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_returns_text_with_disclaimer():
    client = _make_groq_client(complete_text="Phân tích xong.")

    result = await client.complete("system", "Phân tích kết quả")

    assert "Phân tích xong." in result
    assert AI_DISCLAIMER_VI in result


@pytest.mark.asyncio
async def test_complete_handles_none_content():
    """When groq returns None content, should default to empty string."""
    client = _make_groq_client(complete_text=None)

    result = await client.complete("system", "Xét nghiệm")

    assert AI_DISCLAIMER_VI in result


@pytest.mark.asyncio
async def test_complete_raises_on_error():
    client = _make_groq_client(raise_error=True)

    with pytest.raises(RuntimeError, match="Groq API error"):
        await client.complete("system", "user")


@pytest.mark.asyncio
async def test_complete_respects_temperature_and_max_tokens():
    """Test that parameters are forwarded (captured via the fake)."""
    class RecordingCompletions(FakeCompletions):
        captured_kwargs = {}

        async def create(self, **kwargs):
            RecordingCompletions.captured_kwargs = kwargs
            return await super().create(**kwargs)

    client = object.__new__(GroqClient)
    fake_chat = MagicMock()
    fake_chat.completions = RecordingCompletions(complete_text="ok")
    fake_groq = MagicMock()
    fake_groq.chat = fake_chat
    client._client = fake_groq
    client._model = "llama-3.3-70b-versatile"
    client._timeout = 60

    await client.complete("sys", "usr", temperature=0.1, max_tokens=512)

    assert RecordingCompletions.captured_kwargs["temperature"] == pytest.approx(0.1)
    assert RecordingCompletions.captured_kwargs["max_tokens"] == 512
