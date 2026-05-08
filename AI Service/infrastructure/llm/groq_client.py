from __future__ import annotations
import asyncio
import json
from typing import Any, Callable, Generator, Optional, AsyncGenerator
from groq import AsyncGroq
from infrastructure.config import get_settings
from Domain.interfaces import ILLMClient
from Domain.prompts import AI_DISCLAIMER_VI, AI_DISCLAIMER_EN, _detect_language
from infrastructure.llm.tools import TOOLS
import logging

logger = logging.getLogger(__name__)


_TOOL_HANDLERS: dict[str, Any] = {}

_FALLBACK = "[R] Sorry, I can't connect to the AI right now. Please try again later."


def _register_tool_handler(name: str, fn):
    """Allow callers to register tool handlers after GroqClient is instantiated."""
    _TOOL_HANDLERS[name] = fn


class GroqClient(ILLMClient):
    def __init__(self):
        s = get_settings()
        self._client  = AsyncGroq(api_key=s.GROQ_API_KEY)
        self._model   = s.GROQ_TEXT_MODEL
        self._timeout = s.LLM_TIMEOUT_S

    async def stream_completion(
        self,
        system_prompt: str,
        user_prompt:   str,
        temperature:   float = 0.3,
        max_tokens:    int   = 2048,
    ) -> AsyncGenerator[str, None]:
        """Yields text chunks as they arrive. Appends AI disclaimer at the end."""
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

            disclaimer = AI_DISCLAIMER_VI if _detect_language(user_prompt) == "vi" else AI_DISCLAIMER_EN
            yield f"\n\n{disclaimer}"

        except Exception as e:
            logger.error("Groq stream error: %s", e)
            if _detect_language(user_prompt) == "vi":
                yield "[ERROR] Unable to connect to AI. Please try again."
            else:
                yield "[ERROR] Unable to connect to AI. Please try again."

    async def stream_conversation(
        self,
        messages:    list[dict],
        temperature: float = 0.6,
        max_tokens:  int   = 1024,
    ) -> AsyncGenerator[str, None]:
        """
        Multi-turn streaming completion for conversational triage.

        Takes the full messages list (system + history + current user turn).
        Does NOT append the AI disclaimer — the caller owns that responsibility,
        since disclaimers should only appear on final recommendation turns.
        """
        for attempt in range(3):
            try:
                stream = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
                return
            except Exception as e:
                if attempt < 2 and ("429" in str(e) or "rate_limit" in str(e).lower()):
                    logger.warning("Groq rate limit (attempt %d/3), retrying in %ds",
                                   attempt + 1, (attempt + 1) * 5)
                    await asyncio.sleep((attempt + 1) * 5)
                    continue
                logger.error("Groq stream_conversation error: %s", e)
                yield self._fallback_message(messages)
                return

    async def complete(
        self,
        system_prompt: str,
        user_prompt:   str,
        temperature:   float = 0.3,
        max_tokens:    int   = 2048,
        json_mode:     bool  = False,
    ) -> str:
        """Non-streaming completion.

        Args:
            json_mode: When True, returns raw text with no AI disclaimer appended
                       — used for structured/JSON output (e.g. lab suggestions).
        """
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            text = response.choices[0].message.content or ""
            if json_mode:
                return text
            disclaimer = AI_DISCLAIMER_VI if _detect_language(user_prompt) == "vi" else AI_DISCLAIMER_EN
            return f"{text}\n\n{disclaimer}"
        except Exception as e:
            logger.error("Groq complete error: %s", e)
            raise RuntimeError(f"Groq API error: {e}") from e

    async def complete_structured(
        self,
        system_prompt:   str,
        user_prompt:     str,
        response_schema: dict,
        temperature:     float = 0.2,
        max_tokens:      int   = 512,
        max_retries:     int   = 3,
    ) -> dict:
        """
        Non-streaming completion constrained to a JSON schema (Groq JSON mode).
        Returns the parsed JSON dict. Retries on rate-limit errors with
        exponential back-off; falls back to {} after exhausting retries.
        """
        for attempt in range(max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                    response_format={"type": "json_object", "schema": response_schema},
                )
                raw = response.choices[0].message.content or "{}"
                return json.loads(raw)
            except Exception as e:
                is_rl = "429" in str(e) or "rate_limit" in str(e).lower()
                if is_rl and attempt < max_retries - 1:
                    logger.warning("Groq rate limit (attempt %d/%d), retrying in %ds",
                                   attempt + 1, max_retries, (attempt + 1) * 5)
                    await asyncio.sleep((attempt + 1) * 5)
                    continue
                logger.error("Groq complete_structured error: %s", e)
        return {}

    async def stream_with_tools(
        self,
        messages:     list[dict],
        tools:       Optional[list[dict]] = None,
        tool_handler: Optional[Callable[..., Any]] = None,
        temperature: float = 0.6,
        max_tokens:  int = 1024,
    ) -> AsyncGenerator[str, None]:
        """
        Multi-turn streaming completion with tool-calling support.

        When the model emits a tool_calls delta, executes the corresponding
        handler, injects the result as a tool role message, and continues
        streaming until a final text response is produced.

        Args:
            messages: Full conversation list (system + history + current turn).
            tools: List of tool definitions (defaults to TOOLS from tools.py).
            tool_handler: Callable(tool_name, args) -> dict; returns tool result dict.
                          If None, uses the globally registered _TOOL_HANDLERS.
            temperature, max_tokens: LLM parameters.

        Yields:
            Text delta chunks for the final assistant response.
        """
        handler = tool_handler if tool_handler is not None else _TOOL_HANDLERS.get
        tools = tools if tools is not None else TOOLS
        has_tools = bool(tools)

        run_outer = True
        while run_outer:
            run_outer = False
            try:
                stream = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=tools if has_tools else None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
                tcb, ftc = await self._drain_stream(stream)

                for text in ftc:
                    yield text

                if tcb:
                    run_outer = await self._process_tool_calls(tcb, handler, messages)
            except Exception as e:
                logger.error("Groq stream_with_tools error: %s", e)
                async for chunk in self._yield_error_message(messages):
                    yield chunk
                break

    async def _drain_stream(
        self,
        stream,
    ) -> tuple[list[dict], list[str]]:
        """Consume the stream and return (tool_calls_buffer, final_text_chunks)."""
        tcb: list[dict] = []
        ftc: list[str] = []

        async for _tcb, _ftc, _text in self._collect_stream(stream, []):
            tcb, ftc = _tcb, _ftc

        return tcb, ftc

    async def _collect_stream(
        self,
        stream,
        messages: list[dict],
    ) -> AsyncGenerator[tuple[list[dict], list[str], str], None]:
        """Consume the stream, yielding (tool_calls_buffer, final_text_chunks, text_chunk)."""
        tcb: list[dict] = []
        ftc: list[str] = []

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if hasattr(delta, "tool_calls") and delta.tool_calls:
                self._accumulate_tool_calls(delta.tool_calls, tcb)
            elif hasattr(delta, "content") and delta.content:
                ftc.append(delta.content)
                yield tcb, ftc, delta.content

        yield tcb, ftc, ""

    def _accumulate_tool_calls(
        self,
        tool_calls_delta: list,
        buffer: list[dict],
    ) -> None:
        """Merge a tool_calls delta into the buffer, growing it as needed."""
        for tc in tool_calls_delta:
            index = tc.index
            while len(buffer) <= index:
                buffer.append(
                    {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                )
            if tc.id:
                buffer[index]["id"] = tc.id
            func = tc.function
            if func:
                if func.name:
                    buffer[index]["function"]["name"] = func.name
                if func.arguments:
                    buffer[index]["function"]["arguments"] += func.arguments

    async def _process_tool_calls(
        self,
        tool_calls_buffer: list[dict],
        handler: Callable,
        messages: list[dict],
    ) -> bool:
        """Process buffered tool calls, inject results, return True to re-run."""
        for tc in tool_calls_buffer:
            func_name = tc.get("function", {}).get("name", "")
            raw_args  = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(raw_args) if raw_args.startswith("{") else {}
            except json.JSONDecodeError:
                args = {}

            result = handler(func_name, args) if callable(handler) else {
                "error": f"No handler registered for tool '{func_name}'"
            }
            if asyncio.iscoroutine(result):
                result = await result

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "name": func_name,
                "content": json.dumps(result),
            })
        return True  # re-run LLM with tool results

    def _fallback_message(self, messages: list[dict]) -> str:
        last = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        return _FALLBACK

    async def _yield_disclaimer(self, messages: list[dict]) -> AsyncGenerator[str, None, None]:
        lang = _detect_language(
            next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        )
        yield f"\n\n{AI_DISCLAIMER_VI if lang == 'vi' else AI_DISCLAIMER_EN}"

    async def _yield_error_message(self, messages: list[dict]) -> AsyncGenerator[str, None, None]:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        yield _FALLBACK
