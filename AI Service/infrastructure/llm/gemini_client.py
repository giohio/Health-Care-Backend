import json
import re
import httpx
import base64
from infrastructure.config import get_settings
from Domain.interfaces import IVisionClient
from Domain.prompts import ALL_VISION_PROMPTS
import logging

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiClient(IVisionClient):
    def __init__(self):
        s = get_settings()
        self._api_key = s.GEMINI_API_KEY
        self._model   = s.GEMINI_VISION_MODEL
        self._timeout = s.LLM_TIMEOUT_S

    async def extract_findings(
        self,
        image_bytes: bytes,
        mime_type:   str,
        test_type:   str,
        max_retries: int = 2,
    ) -> dict:
        """Sends image to Gemini. Returns parsed JSON findings dict."""
        prompt    = ALL_VISION_PROMPTS.get(test_type, ALL_VISION_PROMPTS["blood_panel"])
        image_b64 = base64.b64encode(image_bytes).decode()

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                ]
            }],
            "generationConfig": {
                "temperature":    0.1,
                "maxOutputTokens": 4096,
            },
        }

        url = (f"{GEMINI_API_BASE}/models/{self._model}"
               f":generateContent?key={self._api_key}")

        raw_text = ""
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                return self._parse_json_safe(raw_text)

            except (KeyError, ValueError) as e:
                logger.warning("Gemini JSON parse attempt %d failed: %s", attempt + 1, e)
                if attempt == max_retries:
                    logger.error("All Gemini retries exhausted")
                    return {"error": "vision_parse_failed", "raw": raw_text[:200]}
            except httpx.HTTPError as e:
                logger.error("Gemini HTTP error: %s", e)
                raise RuntimeError(f"Gemini API error: {e}") from e

    @staticmethod
    def _parse_json_safe(text: str) -> dict:
        """Strip markdown fences and parse JSON."""
        cleaned = re.sub(r"```json|```", "", text).strip()
        return json.loads(cleaned)

    async def extract_tabular(self, tabular_data: dict, _test_type: str) -> dict:
        """For blood panels — sends structured data as text instead of an image."""
        prompt   = ALL_VISION_PROMPTS["blood_panel"]
        data_str = json.dumps(tabular_data, ensure_ascii=False, indent=2)

        payload = {
            "contents": [{"parts": [{"text": f"{prompt}\n\nDATA:\n{data_str}"}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 2048},
        }

        url = (f"{GEMINI_API_BASE}/models/{self._model}"
               f":generateContent?key={self._api_key}")

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return self._parse_json_safe(raw)
