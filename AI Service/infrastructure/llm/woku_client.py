"""WokuClient — OpenAI-compatible LLM client for the Woku gateway.

Implements ILLMClient using the ``openai`` SDK pointed at the Woku base URL
(https://llm.wokushop.com/v1) with model ``gemini-2.5-flash``.

Structurally mirrors GroqClient: same interface, same streaming/tool-calling
pattern, different SDK constructor args.
"""
from __future__ import annotations

import re
JSON_STRIP_RE = r"```(?:json)?\s*|\s*```"

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Callable, Optional

from openai import AsyncOpenAI

from Domain.interfaces import ILLMClient, IVisionClient
from Domain.prompts import AI_DISCLAIMER_EN, AI_DISCLAIMER_VI, _detect_language, ALL_VISION_PROMPTS
from infrastructure.config import get_settings
from infrastructure.llm.tools import TOOLS

logger = logging.getLogger(__name__)

_FALLBACK = "[R] Sorry, I can't connect to the AI right now. Please try again later."


class WokuClient(ILLMClient, IVisionClient):
    """Text + vision LLM client backed by the Woku OpenAI-compatible gateway.

    Pass ``model`` to override the default WOKU_MODEL for a specific use case.
    The underlying AsyncOpenAI client (connection pool) is shared across all
    instances via a class-level singleton to avoid redundant TCP handshakes.
    """

    # Shared connection pool — one per process regardless of how many WokuClient instances exist.
    _shared_openai: AsyncOpenAI | None = None

    @classmethod
    def _get_openai(cls) -> AsyncOpenAI:
        if cls._shared_openai is None:
            s = get_settings()
            cls._shared_openai = AsyncOpenAI(
                api_key=s.WOKU_API_KEY,
                base_url=s.WOKU_BASE_URL,
                timeout=s.LLM_TIMEOUT_S,
                max_retries=0,
            )
        return cls._shared_openai

    def __init__(self, model: str | None = None, fallback_model: str | None = None):
        s = get_settings()
        self._client = self._get_openai()
        self._model = model or s.WOKU_MODEL
        self._fallback_model = fallback_model
        self._timeout = s.LLM_TIMEOUT_S

    # ── ILLMClient interface ──────────────────────────────────

    async def stream_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """Yield text chunks; append AI disclaimer at the end. Retries on rate-limit."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        models_to_try = [self._model]
        if self._fallback_model and self._fallback_model != self._model:
            models_to_try.append(self._fallback_model)

        for model_attempt, active_model in enumerate(models_to_try):
            for attempt in range(3):
                try:
                    stream = await self._client.chat.completions.create(
                        model=active_model,
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

                    disclaimer = AI_DISCLAIMER_VI if _detect_language(user_prompt) == "vi" else AI_DISCLAIMER_EN
                    yield f"\n\n{disclaimer}"
                    return
                except Exception as e:
                    if attempt < 2 and self._is_retryable(e):
                        logger.warning(
                            "Woku stream_completion rate limit model=%s (attempt %d/3), retrying in %ds",
                            active_model, attempt + 1, (attempt + 1) * 5,
                        )
                        await asyncio.sleep((attempt + 1) * 5)
                        continue
                    if model_attempt == 0 and self._fallback_model and self._fallback_model != self._model:
                        logger.warning(
                            "Woku stream_completion switching to fallback model %s after %s",
                            self._fallback_model, e,
                        )
                        break  # break inner loop to try fallback_model
                    logger.error("Woku stream_completion error: %s", e)
                    if _detect_language(user_prompt) == "vi":
                        yield "[Lỗi] Không thể kết nối tới AI. Vui lòng thử lại."
                    else:
                        yield "[ERROR] Unable to connect to AI. Please try again."
                    return

    async def stream_conversation(
        self,
        messages: list[dict],
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Multi-turn streaming completion with retry on rate-limit."""
        models_to_try = [self._model]
        if self._fallback_model and self._fallback_model != self._model:
            models_to_try.append(self._fallback_model)

        for model_attempt, active_model in enumerate(models_to_try):
            for attempt in range(3):
                try:
                    stream = await self._client.chat.completions.create(
                        model=active_model,
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
                    if attempt < 2 and self._is_retryable(e):
                        logger.warning(
                            "Woku stream_conversation rate limit model=%s (attempt %d/3), retrying in %ds",
                            active_model, attempt + 1, (attempt + 1) * 5,
                        )
                        await asyncio.sleep((attempt + 1) * 5)
                        continue
                    if model_attempt == 0 and self._fallback_model and self._fallback_model != self._model:
                        logger.warning(
                            "Woku stream_conversation switching to fallback model %s after %s",
                            self._fallback_model, e,
                        )
                        break
                    logger.error("Woku stream_conversation error: %s", e)
                    yield self._fallback_message(messages)
                    return

    async def stream_with_tools(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        tool_handler: Optional[Callable[..., Any]] = None,
        temperature: float = 0.6,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Streaming completion with tool-calling support (OpenAI function-calling)."""
        handler = tool_handler if tool_handler is not None else lambda name, args: {}
        tools = tools if tools is not None else TOOLS
        has_tools = bool(tools)

        models_to_try = [self._model]
        if self._fallback_model and self._fallback_model != self._model:
            models_to_try.append(self._fallback_model)

        for model_attempt, active_model in enumerate(models_to_try):
            run_outer = True
            used_fallback = model_attempt > 0
            while run_outer:
                run_outer = False
                for attempt in range(3):
                    try:
                        stream = await self._client.chat.completions.create(
                            model=active_model,
                            messages=messages,
                            tools=tools if has_tools else None,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            stream=True,
                        )
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
                                yield delta.content

                        if tcb:
                            run_outer = await self._process_tool_calls(tcb, handler, messages)
                        break  # success — break retry loop
                    except Exception as e:
                        if attempt < 2 and self._is_retryable(e):
                            logger.warning(
                                "Woku stream_with_tools rate limit model=%s (attempt %d/3), retrying in %ds",
                                active_model, attempt + 1, (attempt + 1) * 5,
                            )
                            await asyncio.sleep((attempt + 1) * 5)
                            continue
                        if not used_fallback and self._fallback_model and self._fallback_model != self._model:
                            logger.warning(
                                "Woku stream_with_tools switching to fallback model %s after %s",
                                self._fallback_model, e,
                            )
                            break  # break retry loop to try fallback_model
                        logger.error("Woku stream_with_tools error: %s", e)
                        async for chunk in self._yield_error_message(messages):
                            yield chunk
                        return
                else:
                    # Fallback model triggered — stop iterating models after error handling above
                    continue
                if run_outer:
                    continue  # re-run the outer while loop with same model
                return  # finished cleanly

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        """Non-streaming completion. Appends disclaimer unless json_mode=True."""
        try:
            kwargs = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
                
            response = await self._client.chat.completions.create(**kwargs)
            text = response.choices[0].message.content or ""
            
            if json_mode:
                return re.sub(JSON_STRIP_RE, "", text).strip()
                
            disclaimer = AI_DISCLAIMER_VI if _detect_language(user_prompt) == "vi" else AI_DISCLAIMER_EN
            return f"{text}\n\n{disclaimer}"
        except Exception as e:
            logger.error("Woku complete error: %s", e)
            raise RuntimeError(f"Woku API error: {e}") from e

    async def complete_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict,
        temperature: float = 0.2,
        max_tokens: int = 256,
        max_retries: int = 3,
    ) -> dict:
        """Non-streaming JSON completion using response_format=json_object.

        Falls back to parsing embedded JSON from the raw text when the model
        wraps its output in markdown fences or reasoning text.
        """
        for attempt in range(max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    stream=False,
                )
                raw = response.choices[0].message.content or "{}"
                # Strip markdown fences the model may add
                raw = re.sub(JSON_STRIP_RE, "", raw).strip()
                return json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Woku complete_structured JSON parse error (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {}
            except Exception as e:
                if attempt < max_retries - 1 and self._is_retryable(e):
                    logger.warning(
                        "Woku complete_structured rate limit (attempt %d/%d), retrying",
                        attempt + 1, max_retries,
                    )
                    await asyncio.sleep((attempt + 1) * 5)
                    continue
                logger.error("Woku complete_structured error: %s", e)
        return {}

    # ── IVisionClient interface ─────────────────────────────────

    async def extract_findings(
        self,
        image_bytes: bytes,
        mime_type: str,
        test_type: str,
        max_retries: int = 2,
    ) -> dict:
        """Extract structured findings from an image via OpenAI vision messages.
        Falls back to text-only analysis if vision channels are unavailable.
        """
        prompt = ALL_VISION_PROMPTS.get(test_type, ALL_VISION_PROMPTS["blood_panel"])
        # Only attempt vision for true image types; PDFs not supported via image_url
        is_image = mime_type.startswith("image/")
        if is_image:
            import base64
            image_b64 = base64.b64encode(image_bytes).decode()
            data_url = f"data:{mime_type};base64,{image_b64}"

            for attempt in range(max_retries + 1):
                try:
                    # Simplified message structure for maximum gateway compatibility
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"You are a specialized medical AI assistant. Extract data precisely as JSON.\n\n{prompt}"},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }
                    ]

                    response = await self._client.chat.completions.create(
                        model=self._model,
                        messages=messages,
                        temperature=0.1,
                        max_tokens=4096,
                        stream=False,
                    )
                    raw = response.choices[0].message.content or "{}"
                    raw = re.sub(JSON_STRIP_RE, "", raw).strip()
                    # If the model wrapped JSON in reasoning text, extract first {...} block
                    if not raw.startswith("{"):
                        m = re.search(r"\{.*\}", raw, re.DOTALL)
                        raw = m.group(0) if m else raw
                    return json.loads(raw)

                except json.JSONDecodeError as e:
                    logger.warning("Woku extract_findings JSON parse error (attempt %d): %s", attempt + 1, e)
                    if attempt == max_retries:
                        break
                except Exception as e:
                    logger.warning("Woku vision attempt %d failed: %s", attempt + 1, e)
                    if attempt == max_retries:
                        break
                    # Continue to next attempt instead of breaking immediately
                    await asyncio.sleep(1)

        # Text-only fallback: ask the LLM to produce a *compact* findings summary
        # based on the test type alone (no image data available).
        logger.info("Woku extract_findings: using text-only fallback for mime_type=%s", mime_type)
        simple_fallback_prompt = (
            f"You are a medical AI assistant. A lab test of type '{test_type}' was submitted "
            "but the file could not be parsed as an image. "
            "Return a SHORT JSON object (under 200 tokens) with these fields only: "
            '{"summary": "<one-sentence description>", "requires_manual_review": true, '
            '"confidence": 0.3, "_fallback": true}. '
            "Do NOT include any other fields. Output only valid JSON, no markdown."
        )
        for fb_attempt in range(2):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": simple_fallback_prompt}],
                    temperature=0.1,
                    max_tokens=256,
                    stream=False,
                )
                raw = response.choices[0].message.content or "{}"
                raw = re.sub(JSON_STRIP_RE, "", raw).strip()
                result = json.loads(raw)
                result["_fallback"] = True
                return result
            except json.JSONDecodeError as e:
                logger.warning(
                    "Woku extract_findings text fallback JSON parse error (attempt %d): %s — raw: %.200s",
                    fb_attempt + 1, e, raw,
                )
                if fb_attempt == 0:
                    # retry with an even simpler prompt
                    simple_fallback_prompt = (
                        f'Return only this JSON: {{"summary": "Lab result for {test_type} requires manual review.", '
                        '"requires_manual_review": true, "confidence": 0.3}}'
                    )
                    continue
                # Give up parsing — return a hardcoded minimal result so the
                # synthesis pipeline can still run and produce a useful draft.
                return {
                    "summary": f"Lab result for {test_type} — automated extraction failed, manual review required.",
                    "requires_manual_review": True,
                    "confidence": 0.3,
                    "_fallback": True,
                }
            except Exception as e:
                logger.error("Woku extract_findings text fallback API error (attempt %d): %s", fb_attempt + 1, e)
                break
        return {
            "summary": f"Lab result for {test_type} — automated extraction failed, manual review required.",
            "requires_manual_review": True,
            "confidence": 0.3,
            "_fallback": True,
        }

    async def extract_tabular(
        self,
        tabular_data: dict,
        test_type: str,
        max_retries: int = 2,
    ) -> dict:
        """Extract structured findings from tabular/CSV lab data.

        Uses a text-only prompt (no image). Handles JSON extraction robustly
        with retries and a fallback result so the Celery pipeline never stalls.
        """
        prompt = ALL_VISION_PROMPTS.get(test_type, ALL_VISION_PROMPTS["blood_panel"])
        data_str = json.dumps(tabular_data, ensure_ascii=False, indent=2)
        full_prompt = f"{prompt}\n\nLab data:\n{data_str}"

        for attempt in range(max_retries + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": full_prompt}],
                    temperature=0.1,
                    max_tokens=2048,  # increased — blood panel JSON can be large
                    stream=False,
                )
                raw = response.choices[0].message.content or "{}"
                raw = re.sub(JSON_STRIP_RE, "", raw).strip()
                # If model wrapped JSON in reasoning text, pull out first {...} block
                if not raw.startswith("{"):
                    m = re.search(r"\{.*\}", raw, re.DOTALL)
                    raw = m.group(0) if m else raw
                return json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Woku extract_tabular JSON parse error (attempt %d): %s — raw snippet: %.200s",
                    attempt + 1, e, raw,
                )
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue
            except Exception as e:
                logger.error("Woku extract_tabular API error (attempt %d): %s", attempt + 1, e)
                if attempt < max_retries:
                    await asyncio.sleep(1)
                    continue
                break

        # All attempts failed — return a minimal valid result so the Celery pipeline
        # can still produce a NEEDS_MANUAL_REVIEW status rather than hanging at PENDING.
        logger.error("Woku extract_tabular: all %d attempts failed, using fallback", max_retries + 1)
        return {"error": "tabular_parse_failed"}

    # ── Internal helpers ──────────────────────────────────────

    def _fallback_message(self, messages: list[dict]) -> str:
        return _FALLBACK

    def _is_retryable(self, exc: Exception) -> bool:
        s = str(exc).lower()
        return "429" in s or "rate_limit" in s or "rate limit" in s

    def _accumulate_tool_calls(self, tool_calls_delta: list, buffer: list[dict]) -> None:
        """Merge a tool_calls delta into the accumulation buffer."""
        for tc in tool_calls_delta:
            index = tc.index
            while len(buffer) <= index:
                buffer.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
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
        """Execute buffered tool calls, inject results into messages, return True to re-run."""
        for tc in tool_calls_buffer:
            func_name = tc.get("function", {}).get("name", "")
            raw_args = tc.get("function", {}).get("arguments", "{}")
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
        return True

    async def _yield_disclaimer(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        lang = _detect_language(
            next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        )
        yield f"\n\n{AI_DISCLAIMER_VI if lang == 'vi' else AI_DISCLAIMER_EN}"

    async def _yield_error_message(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        yield _FALLBACK
