"""
Unit tests for infrastructure/llm/woku_client.py

Uses Fake objects injected into WokuClient internals to avoid any real API
calls — no tokens are consumed. Structure mirrors test_groq_client.py.
"""
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import MagicMock

from infrastructure.llm.woku_client import WokuClient
from Domain.prompts import AI_DISCLAIMER_VI, AI_DISCLAIMER_EN


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------

class FakeStreamChunk:
    """Mimics one token chunk returned by the openai async stream."""
    def __init__(self, content, tool_calls=None):
        delta = MagicMock()
        delta.content = content
        delta.tool_calls = tool_calls
        self.choices = [MagicMock(delta=delta)]


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
    """Fake chat.completions supporting stream=True and stream=False."""

    def __init__(self, stream_chunks=None, complete_text="", raise_error=None):
        self._stream_chunks = stream_chunks or []
        self._complete_text = complete_text
        self._raise_error = raise_error

    async def create(self, **kwargs):
        await asyncio.sleep(0)
        if self._raise_error is not None:
            raise self._raise_error
        if kwargs.get("stream"):
            return FakeAsyncStream(self._stream_chunks)
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content=self._complete_text))]
        return resp


def _make_woku_client(stream_chunks=None, complete_text="", raise_error=None) -> WokuClient:
    """Build a WokuClient wired to Fake internals — no real API key needed."""
    client = object.__new__(WokuClient)
    fake_completions = FakeCompletions(stream_chunks, complete_text, raise_error)
    fake_chat = MagicMock()
    fake_chat.completions = fake_completions
    fake_openai = MagicMock()
    fake_openai.chat = fake_chat
    client._client = fake_openai
    client._model = "gemini-2.5-flash"
    client._fallback_model = None
    client._timeout = 60
    return client


# ---------------------------------------------------------------------------
# stream_completion tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_completion_yields_all_chunks():
    chunks = [FakeStreamChunk("Xin"), FakeStreamChunk(" chào"), FakeStreamChunk("!")]
    client = _make_woku_client(stream_chunks=chunks)

    result = []
    async for token in client.stream_completion("system", "Xin chào bạn"):
        result.append(token)

    assert result == ["Xin", " chào", "!", f"\n\n{AI_DISCLAIMER_VI}"]


@pytest.mark.asyncio
async def test_stream_completion_skips_none_deltas():
    chunks = [FakeStreamChunk("Hello"), FakeStreamChunk(None), FakeStreamChunk(" world")]
    client = _make_woku_client(stream_chunks=chunks)

    result = []
    async for token in client.stream_completion("system", "user"):
        result.append(token)

    assert "Hello" in result
    assert " world" in result
    assert None not in result


@pytest.mark.asyncio
async def test_stream_completion_appends_vi_disclaimer_for_vietnamese():
    client = _make_woku_client(stream_chunks=[FakeStreamChunk("Kết quả.")])

    last_chunk = None
    async for token in client.stream_completion("system", "Kết quả xét nghiệm"):
        last_chunk = token

    assert AI_DISCLAIMER_VI in last_chunk


@pytest.mark.asyncio
async def test_stream_completion_appends_en_disclaimer_for_english():
    client = _make_woku_client(stream_chunks=[FakeStreamChunk("Result.")])

    last_chunk = None
    async for token in client.stream_completion("system", "blood test result"):
        last_chunk = token

    assert AI_DISCLAIMER_EN in last_chunk


@pytest.mark.asyncio
async def test_stream_completion_error_yields_error_message():
    client = _make_woku_client(raise_error=RuntimeError("API down"))

    result = []
    async for token in client.stream_completion("system", "Xét nghiệm máu"):
        result.append(token)

    assert len(result) == 1
    assert "[Lỗi]" in result[0]


@pytest.mark.asyncio
async def test_stream_completion_error_en_message():
    client = _make_woku_client(raise_error=RuntimeError("API down"))

    result = []
    async for token in client.stream_completion("system", "blood test"):
        result.append(token)

    assert len(result) == 1
    assert "[ERROR]" in result[0]


# ---------------------------------------------------------------------------
# complete tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_returns_text_with_vi_disclaimer():
    client = _make_woku_client(complete_text="Phân tích xong.")

    result = await client.complete("system", "Phân tích kết quả")

    assert "Phân tích xong." in result
    assert AI_DISCLAIMER_VI in result


@pytest.mark.asyncio
async def test_complete_json_mode_no_disclaimer():
    client = _make_woku_client(complete_text='{"key": "value"}')

    result = await client.complete("system", "Parse this", json_mode=True)

    assert result == '{"key": "value"}'
    assert AI_DISCLAIMER_VI not in result
    assert AI_DISCLAIMER_EN not in result


@pytest.mark.asyncio
async def test_complete_handles_none_content():
    client = _make_woku_client(complete_text=None)

    result = await client.complete("system", "Xét nghiệm")

    assert AI_DISCLAIMER_VI in result


@pytest.mark.asyncio
async def test_complete_raises_on_error():
    client = _make_woku_client(raise_error=RuntimeError("503"))

    with pytest.raises(RuntimeError, match="Woku API error"):
        await client.complete("system", "user")


@pytest.mark.asyncio
async def test_complete_passes_temperature_and_max_tokens():
    class RecordingCompletions(FakeCompletions):
        captured: dict = {}

        async def create(self, **kwargs):
            RecordingCompletions.captured = kwargs
            return await super().create(**kwargs)

    client = object.__new__(WokuClient)
    fake_chat = MagicMock()
    fake_chat.completions = RecordingCompletions(complete_text="ok")
    fake_openai = MagicMock()
    fake_openai.chat = fake_chat
    client._client = fake_openai
    client._model = "gemini-2.5-flash"
    client._fallback_model = None
    client._timeout = 60

    await client.complete("sys", "usr", temperature=0.1, max_tokens=512)

    assert RecordingCompletions.captured["temperature"] == pytest.approx(0.1)
    assert RecordingCompletions.captured["max_tokens"] == 512


# ---------------------------------------------------------------------------
# stream_conversation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_conversation_yields_chunks():
    chunks = [FakeStreamChunk("こんにちは"), FakeStreamChunk("！")]
    client = _make_woku_client(stream_chunks=chunks)

    messages = [{"role": "user", "content": "Hello"}]
    result = []
    async for token in client.stream_conversation(messages):
        result.append(token)

    assert result == ["こんにちは", "！"]


@pytest.mark.asyncio
async def test_stream_conversation_falls_back_on_error():
    client = _make_woku_client(raise_error=RuntimeError("network error"))

    messages = [{"role": "user", "content": "Xin chào"}]
    result = []
    async for token in client.stream_conversation(messages):
        result.append(token)

    assert len(result) == 1
    # Vietnamese message → VI fallback
    assert "Xin lỗi" in result[0]


# ---------------------------------------------------------------------------
# complete_structured tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_structured_returns_parsed_dict():
    client = _make_woku_client(complete_text='{"specialties": ["Neurology"]}')

    result = await client.complete_structured("sys", "user", response_schema={})

    assert result == {"specialties": ["Neurology"]}


@pytest.mark.asyncio
async def test_complete_structured_strips_markdown_fences():
    client = _make_woku_client(complete_text='```json\n{"a": 1}\n```')

    result = await client.complete_structured("sys", "user", response_schema={})

    assert result == {"a": 1}


@pytest.mark.asyncio
async def test_complete_structured_returns_empty_on_invalid_json():
    client = _make_woku_client(complete_text="not json at all")

    result = await client.complete_structured("sys", "user", response_schema={}, max_retries=1)

    assert result == {}


@pytest.mark.asyncio
async def test_complete_structured_returns_empty_on_api_error():
    client = _make_woku_client(raise_error=RuntimeError("500"))

    result = await client.complete_structured("sys", "user", response_schema={}, max_retries=1)

    assert result == {}


# ---------------------------------------------------------------------------
# stream_with_tools tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_with_tools_yields_text_chunks():
    """No tool calls — just text chunks with disclaimer appended."""
    chunks = [FakeStreamChunk("Triệu chứng"), FakeStreamChunk(" bình thường.")]
    client = _make_woku_client(stream_chunks=chunks)

    messages = [{"role": "user", "content": "Đau đầu nhẹ"}]
    result = []
    async for token in client.stream_with_tools(messages, tools=[]):
        result.append(token)

    combined = "".join(result)
    assert "Triệu chứng" in combined
    assert " bình thường." in combined
    assert AI_DISCLAIMER_VI in combined


@pytest.mark.asyncio
async def test_stream_with_tools_handles_error():
    client = _make_woku_client(raise_error=RuntimeError("timeout"))

    messages = [{"role": "user", "content": "test"}]
    result = []
    async for token in client.stream_with_tools(messages, tools=[]):
        result.append(token)

    assert len(result) == 1


# ---------------------------------------------------------------------------
# _accumulate_tool_calls tests
# ---------------------------------------------------------------------------

def test_accumulate_tool_calls_builds_buffer():
    client = object.__new__(WokuClient)
    buffer: list[dict] = []

    delta1 = MagicMock()
    delta1.index = 0
    delta1.id = "call_abc"
    delta1.function = MagicMock()
    delta1.function.name = "get_doctors"
    delta1.function.arguments = '{"spec'

    delta2 = MagicMock()
    delta2.index = 0
    delta2.id = None
    delta2.function = MagicMock()
    delta2.function.name = None
    delta2.function.arguments = 'ialty": "Neurology"}'

    client._accumulate_tool_calls([delta1], buffer)
    client._accumulate_tool_calls([delta2], buffer)

    assert buffer[0]["id"] == "call_abc"
    assert buffer[0]["function"]["name"] == "get_doctors"
    assert json.loads(buffer[0]["function"]["arguments"]) == {"specialty": "Neurology"}


# ---------------------------------------------------------------------------
# WokuClient implements ILLMClient
# ---------------------------------------------------------------------------

def test_woku_client_is_illm_client():
    from Domain.interfaces import ILLMClient
    assert issubclass(WokuClient, ILLMClient)
