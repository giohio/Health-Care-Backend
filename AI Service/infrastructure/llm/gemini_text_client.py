"""Gemini text client — implements ILLMClient for general-purpose LLM calls."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator, Callable, Optional

import httpx

from Domain.interfaces import ILLMClient
from Domain.prompts import AI_DISCLAIMER_EN, AI_DISCLAIMER_VI, _detect_language
from infrastructure.config import get_settings

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_SSE_DATA = "data:"
_DONE_SENTINEL = "[DONE]"
_FALLBACK = "[R] Sorry, I can't connect to the AI right now. Please try again later."


def _extract_json_from_text(text: str) -> dict | None:
    """
    Extract the first valid JSON object `{...}` embedded in reasoning/thinking text.

    Gemini thinking models sometimes return:
        "* Reasoning...\n* JSON format: `{\"specialties\": [\"Neurology\"]}`"
    instead of pure JSON.  This helper finds and returns the embedded object.
    """
    for m in re.finditer(r'\{[^{}]*\}', text):
        try:
            obj = json.loads(m.group())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


class GeminiTextClient(ILLMClient):
    """Text LLM client backed by Google Gemini API via httpx."""

    # Shared across all instances — avoids per-request TCP+TLS handshake.
    _shared_client: httpx.AsyncClient | None = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        if cls._shared_client is None or cls._shared_client.is_closed:
            s = get_settings()
            cls._shared_client = httpx.AsyncClient(
                timeout=s.LLM_TIMEOUT_S,
                http2=True,
            )
        return cls._shared_client

    @classmethod
    async def aclose(cls) -> None:
        """Close the shared client. Call on application shutdown."""
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None

    def __init__(self, model: str | None = None):
        s = get_settings()
        self._api_key = s.GEMINI_API_KEY
        self._model = model or s.GEMINI_TEXT_MODEL
        self._timeout = s.LLM_TIMEOUT_S

    # ── ILLMClient interface ──────────────────────────────────

    async def stream_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        messages = [
            {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]},
        ]
        async for chunk in self._stream(messages, temperature, max_tokens):
            yield chunk

    async def stream_conversation(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ) -> AsyncGenerator[str, None]:
        gemini_msgs = self._convert_messages(messages)
        for attempt in range(3):
            try:
                async for chunk in self._stream(gemini_msgs, temperature, max_tokens):
                    yield chunk
                return
            except Exception as e:
                if attempt < 2 and self._is_retryable(e):
                    logger.warning("Gemini rate limit (attempt %d/3), retrying in %ds",
                                   attempt + 1, (attempt + 1) * 5)
                    await asyncio.sleep((attempt + 1) * 5)
                    continue
                logger.error("Gemini stream_conversation error: %s", e)
                yield self._fallback_message(messages)
                return

    async def stream_with_tools(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        tool_handler: Optional[Callable[..., Any]] = None,
        temperature: float = 0.6,
        max_tokens: int = 512,
    ) -> AsyncGenerator[str, None]:
        """
        Real-time streaming with tool-calling for Gemma-4 via Gemini API.

        Algorithm (mirrors GroqClient approach):
          1. Stream text chunks to caller as they arrive (first turn).
          2. If a functionCall part is detected mid-stream → execute the tool,
             inject the result, then stream the second turn directly.
          3. No disclaimer appended here — caller owns that.

        Uses an asyncio.Queue so the SSE reader can push chunks while
        the outer async generator pops and yields them to the caller
        without buffering the full response.
        """
        if tools is None:
            tools = []

        gemini_msgs = self._convert_messages(messages)

        # ── First turn: stream with tool detection ───────────────────────────────
        q: asyncio.Queue[str | None] = asyncio.Queue()

        async def stream_task():
            """Read SSE, push text to queue, detect functionCall."""
            fc = await self._stream_one_turn(
                gemini_msgs, temperature, max_tokens, tools, q.put_nowait,
            )
            await q.put(None)  # sentinel: stream done
            return fc

        task = asyncio.create_task(stream_task())

        # Yield chunks from first turn until done or tool detected
        while True:
            chunk = await q.get()
            if chunk is None:  # sentinel
                break
            yield chunk

        func_call = await task
        
        # ── Execute tool if functionCall detected ─────────────────────────────
        if func_call is not None:
            tool_name = func_call.get("name", "")
            tool_args = func_call.get("args", {})
            logger.info("Gemini Gemma-4 function_call: %s(%s)", tool_name, tool_args)

            if tool_handler is not None:
                result = await tool_handler(tool_name, tool_args)
            else:
                result = {"status": "error", "message": f"No handler registered for tool: {tool_name}"}

            gemini_msgs.append({"role": "model", "parts": [{"functionCall": func_call}]})
            gemini_msgs.append({
                "role": "user",
                "parts": [{"functionResponse": {"name": tool_name, "response": result}}],
            })

            # ── Second turn: stream final response directly to caller ───────────
            async for raw in self._stream_raw(gemini_msgs, temperature, max_tokens, tools):
                for _ in self._extract_function_calls_from_raw(raw):
                    # A functionCall in turn 2 would be recursive — not expected
                    pass
                for text in self._extract_text_parts(raw):
                    yield text

    async def _stream_one_turn(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: list[dict],
        push: Callable[[str], Any],
    ) -> dict | None:
        """
        Stream one LLM turn, pushing text chunks via `push`.

        Returns the function_call dict if a functionCall was detected,
        otherwise None.
        """
        payload = self._build_payload(messages, temperature, max_tokens, tools)
        url = (f"{GEMINI_API_BASE}/models/{self._model}"
               f":streamGenerateContent?key={self._api_key}&alt=sse")

        func_call: dict | None = None

        for attempt in range(3):
            try:
                client = self._get_client()
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for raw in self._iter_sse_lines(resp):
                        if not raw or raw == _DONE_SENTINEL:
                            continue
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        for cand in data.get("candidates", []):
                            for part in cand.get("content", {}).get("parts", []):
                                if part.get("thought"):
                                    continue
                                if "text" in part:
                                    push(part["text"])
                                elif "functionCall" in part:
                                    fc = part["functionCall"]
                                    raw_args = fc.get("args", {})
                                    if isinstance(raw_args, str):
                                        try:
                                            raw_args = json.loads(raw_args)
                                        except json.JSONDecodeError:
                                            raw_args = {}
                                    func_call = {
                                        "name": fc.get("name", ""),
                                        "args": raw_args,
                                        "id":   fc.get("id", ""),
                                    }
                return func_call
            except Exception as e:
                if attempt < 2 and self._is_retryable(e):
                    logger.warning("_stream_one_turn retry (attempt %d/3): %s",
                                   attempt + 1, e)
                    await asyncio.sleep((attempt + 1) * 5)
                    continue
                logger.error("_stream_one_turn error: %s", e)
                return func_call

        return func_call

    async def _stream_raw(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """Yield raw SSE data lines from the Gemini streaming endpoint."""
        payload = self._build_payload(messages, temperature, max_tokens, tools)
        url = (f"{GEMINI_API_BASE}/models/{self._model}"
               f":streamGenerateContent?key={self._api_key}&alt=sse")
        for attempt in range(3):
            try:
                client = self._get_client()
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for raw in self._iter_sse_lines(resp):
                        yield raw
                return
            except Exception as e:
                if attempt < 2 and self._is_retryable(e):
                    logger.warning("_stream_raw retry (attempt %d/3): %s", attempt + 1, e)
                    await asyncio.sleep((attempt + 1) * 5)
                    continue
                logger.error("_stream_raw error: %s", e)
                return

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        messages = [
            {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]},
        ]
        for attempt in range(3):
            try:
                text = await self._complete(messages, temperature, max_tokens,
                                             json_mode=json_mode)
                if json_mode:
                    return text
                lang = _detect_language(user_prompt)
                disc = AI_DISCLAIMER_VI if lang == "vi" else AI_DISCLAIMER_EN
                return f"{text}\n\n{disc}"
            except Exception as e:
                if attempt < 2 and self._is_retryable(e):
                    logger.warning("Gemini complete rate limit (attempt %d/3), retrying",
                                   attempt + 1)
                    await asyncio.sleep((attempt + 1) * 5)
                    continue
                logger.error("Gemini complete error: %s", e)
                raise RuntimeError(f"Gemini API error: {e}") from e
        return ""

    async def complete_structured(
        self,
        system_prompt:   str,
        user_prompt:     str,
        response_schema: dict,
        temperature:     float = 0.2,
        max_tokens:      int   = 256,
        max_retries:     int   = 3,
    ) -> dict:
        """Constrained JSON completion using a schema, with retry on rate-limit."""
        messages = [
            {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]},
        ]
        payload = self._build_payload(messages, temperature, max_tokens)
        # NOTE: responseMimeType="application/json" is NOT supported by Gemma models
        # (only Gemini 1.5/2.0). Omit it and parse JSON robustly from the text response.
        url = (f"{GEMINI_API_BASE}/models/{self._model}"
               f":generateContent?key={self._api_key}")
        for attempt in range(max_retries):
            try:
                client = self._get_client()
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                # Gemma may return an empty parts list or finish_reason=OTHER
                candidates = data.get("candidates", [])
                if not candidates:
                    logger.warning("complete_structured: no candidates in response")
                    if attempt < max_retries - 1:
                        await asyncio.sleep((attempt + 1) * 3)
                        continue
                    return {}
                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts or not parts[0].get("text"):
                    finish = candidates[0].get("finishReason", "unknown")
                    logger.warning("complete_structured: empty text, finishReason=%s", finish)
                    if attempt < max_retries - 1:
                        await asyncio.sleep((attempt + 1) * 3)
                        continue
                    return {}
                text = parts[0]["text"]
                # Strip markdown code fences that Gemma sometimes wraps JSON in
                text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
                if not text:
                    logger.warning("complete_structured: text empty after fence-strip")
                    if attempt < max_retries - 1:
                        await asyncio.sleep((attempt + 1) * 3)
                        continue
                    return {}
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    pass
                # Gemini thinking models output reasoning around the JSON.
                # Try to extract the first embedded JSON object from the text.
                extracted = _extract_json_from_text(text)
                if extracted is not None:
                    return extracted
            except json.JSONDecodeError as e:
                # Also try embedded extraction for outer parse failures
                if 'text' in dir():
                    extracted = _extract_json_from_text(text)
                    if extracted is not None:
                        return extracted
                logger.warning("complete_structured JSON parse error (attempt %d/%d): %s | text=%r",
                               attempt + 1, max_retries, e, text[:300] if 'text' in dir() else '')
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)   # reduced: was (attempt+1)*3s = 3s/6s/9s
                    continue
                return {}
            except Exception as e:
                if attempt < max_retries - 1 and self._is_rate_limit(e):
                    logger.warning("Gemini complete_structured rate limit (attempt %d/%d), retrying",
                                   attempt + 1, max_retries)
                    await asyncio.sleep((attempt + 1) * 5)
                    continue
                logger.error("Gemini complete_structured error: %s", e)
        return {}

    # ── Internal helpers ──────────────────────────────────────

    def _fallback_message(self, messages: list[dict]) -> str:
        return _FALLBACK

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert OpenAI-style messages to Gemini format.

        Remaps roles:
          - 'system'    → kept as 'system' so _build_payload can extract to systemInstruction
          - 'assistant' → 'model'  (Gemini role name)
          - 'user'      → 'user'   (unchanged)
        """
        _ROLE_MAP = {"assistant": "model"}
        converted = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts = self._extract_parts(content)
            if role == "system":
                # Keep role='system' intact — _build_payload lifts it to systemInstruction.
                # Previously this was skipped with `continue` which silently dropped the
                # system prompt before _build_payload ever saw it.
                converted.append({"role": "system", "parts": parts})
                continue
            role = _ROLE_MAP.get(role, role)
            converted.append({"role": role, "parts": parts})
        return converted

    def _extract_parts(self, content: str | list) -> list[dict]:
        """Extract Gemini parts from content string or list."""
        if isinstance(content, str):
            return [{"text": content}]
        if not isinstance(content, list):
            return []
        parts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                parts.append({"text": part.get("text", "")})
            elif part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                if _SSE_DATA in url:
                    parts.append(self._parse_inline_data(url))
        return parts

    def _parse_inline_data(self, url: str) -> dict:
        """Parse base64 inline data URL into Gemini inline_data part."""
        _, data = url.split(";base64,", 1)
        mime = url.split(";base64,", 1)[0].replace(_SSE_DATA, "")
        return {"inline_data": {"mime_type": mime, "data": data}}

    def _build_payload(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        # Separate system messages → systemInstruction (Gemini doesn't support role='system' in contents)
        sys_parts: list[dict] = []
        contents: list[dict] = []
        for m in messages:
            if m.get("role") == "system":
                sys_parts.extend(m.get("parts", [{"text": m.get("content", "")}]))
            else:
                contents.append(m)

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if sys_parts:
            payload["systemInstruction"] = {"parts": sys_parts}
        if tools:
            declarations = []
            for tool in tools:
                func = tool.get("function", {})
                declarations.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {"type": "object", "properties": {}}),
                })
            payload["tools"] = [{"function_declarations": declarations}]
        return payload

    async def _stream(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        payload = self._build_payload(messages, temperature, max_tokens, tools)
        url = (f"{GEMINI_API_BASE}/models/{self._model}"
               f":streamGenerateContent?key={self._api_key}&alt=sse")
        client = self._get_client()
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for raw in self._iter_sse_lines(resp):
                for text in self._extract_text_parts(raw):
                    yield text

    async def _iter_sse_lines(self, resp) -> AsyncGenerator[str, None]:
        async for chunk in resp.aiter_lines():
            if chunk.startswith(_SSE_DATA):
                yield chunk[len(_SSE_DATA):].strip()

    def _extract_text_parts(self, raw: str) -> list[str]:
        """Extract text content from a raw SSE JSON line, skipping thought parts."""
        if not raw or raw == _DONE_SENTINEL:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        texts = []
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                if part.get("thought"):
                    continue
                if "text" in part:
                    texts.append(part["text"])
        return texts

    def _extract_function_calls_from_raw(self, raw: str) -> list[dict]:
        """Extract all functionCall dicts from a raw SSE JSON line."""
        if not raw or raw == _DONE_SENTINEL:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        calls = []
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                if "functionCall" in part:
                    fc = part["functionCall"]
                    raw_args = fc.get("args", {})
                    if isinstance(raw_args, str):
                        try:
                            raw_args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            raw_args = {}
                    calls.append({
                        "name": fc.get("name", ""),
                        "args": raw_args,
                        "id":   fc.get("id", ""),
                    })
        return calls

    async def _complete(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        payload = self._build_payload(messages, temperature, max_tokens)
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        url = (f"{GEMINI_API_BASE}/models/{self._model}"
               f":generateContent?key={self._api_key}")
        client = self._get_client()
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        if json_mode:
            return text
        return re.sub(r"```json|```", "", text).strip()

    @staticmethod
    def _is_rate_limit(e: Exception) -> bool:
        s = str(e).lower()
        return any(k in s for k in ("429", "rate_limit", "quota", "resource_exhausted"))

    @staticmethod
    def _is_server_error(e: Exception) -> bool:
        s = str(e).lower()
        return any(k in s for k in ("500", "502", "503", "internal server error"))

    @staticmethod
    def _is_retryable(e: Exception) -> bool:
        return GeminiTextClient._is_rate_limit(e) or GeminiTextClient._is_server_error(e)
