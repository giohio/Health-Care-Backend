"""
Unit tests for infrastructure/llm/gemini_client.py

Uses monkeypatching and Fake httpx responses to avoid real network calls.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.llm.gemini_client import GeminiClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gemini_client() -> GeminiClient:
    """Build GeminiClient bypassing real settings / API key."""
    client = object.__new__(GeminiClient)
    client._api_key = "fake-api-key"
    client._model = "gemini-1.5-flash"
    client._timeout = 60
    return client


def _mock_httpx_post(response_json: dict, raise_http_error=False):
    """Context manager factory that patches httpx.AsyncClient to return a fake response."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    if raise_http_error:
        import httpx
        mock_resp.raise_for_status.side_effect = httpx.HTTPError("HTTP Error")
    mock_resp.json.return_value = response_json

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    return patch("httpx.AsyncClient", return_value=mock_client)


def _gemini_response(text: str) -> dict:
    """Build a minimal Gemini API response structure."""
    return {
        "candidates": [{
            "content": {
                "parts": [{"text": text}]
            }
        }]
    }


# ---------------------------------------------------------------------------
# _parse_json_safe tests
# ---------------------------------------------------------------------------

def test_parse_json_safe_clean_json():
    client = _make_gemini_client()
    result = client._parse_json_safe('{"findings": "normal", "confidence": 0.9}')
    assert result["findings"] == "normal"
    assert result["confidence"] == pytest.approx(0.9)


def test_parse_json_safe_strips_markdown_fences():
    client = _make_gemini_client()
    text = "```json\n{\"key\": \"value\"}\n```"
    result = client._parse_json_safe(text)
    assert result["key"] == "value"


def test_parse_json_safe_strips_bare_fences():
    client = _make_gemini_client()
    text = "```\n{\"key\": \"value\"}\n```"
    result = client._parse_json_safe(text)
    assert result["key"] == "value"


# ---------------------------------------------------------------------------
# extract_findings tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_findings_success():
    findings_json = '{"impression": "No acute findings", "confidence": 0.88}'
    response = _gemini_response(findings_json)

    client = _make_gemini_client()
    with _mock_httpx_post(response):
        result = await client.extract_findings(b"fake-image-bytes", "image/jpeg", "chest_xray")

    assert result["impression"] == "No acute findings"
    assert result["confidence"] == pytest.approx(0.88)


@pytest.mark.asyncio
async def test_extract_findings_with_markdown_fence():
    findings_json = "```json\n{\"diagnosis\": \"ECG normal\"}\n```"
    response = _gemini_response(findings_json)

    client = _make_gemini_client()
    with _mock_httpx_post(response):
        result = await client.extract_findings(b"bytes", "image/jpeg", "ecg")

    assert result["diagnosis"] == "ECG normal"


@pytest.mark.asyncio
async def test_extract_findings_returns_error_after_max_retries():
    """JSON parse consistently fails — should return error dict after max_retries."""
    response = _gemini_response("this is not valid JSON at all!!!")

    client = _make_gemini_client()
    with _mock_httpx_post(response):
        result = await client.extract_findings(b"bytes", "image/jpeg", "brain_mri", max_retries=1)

    assert result.get("error") == "vision_parse_failed"
    assert "raw" in result


@pytest.mark.asyncio
async def test_extract_findings_http_error_propagates():
    """HTTP errors should propagate as RuntimeError, not be swallowed."""
    import httpx

    client = _make_gemini_client()
    with _mock_httpx_post({}, raise_http_error=True):
        with pytest.raises(RuntimeError, match="Gemini API error"):
            await client.extract_findings(b"bytes", "image/jpeg", "blood_panel")


@pytest.mark.asyncio
async def test_extract_findings_uses_correct_vision_prompt_key(monkeypatch):
    """Verify it selects the correct prompt from VISION_PROMPTS."""
    findings_json = '{"ok": true}'
    response = _gemini_response(findings_json)

    captured_payload = {}

    async def fake_post(url, json, **kwargs):
        await asyncio.sleep(0)
        captured_payload.update(json)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = response
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    client = _make_gemini_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        await client.extract_findings(b"bytes", "image/png", "fundus")

    # The prompt should reference fundus-specific instructions
    from Domain.prompts import VISION_PROMPTS
    fundus_prompt = VISION_PROMPTS["fundus"]
    assert fundus_prompt in captured_payload["contents"][0]["parts"][0]["text"]


@pytest.mark.asyncio
async def test_extract_findings_uses_auscultation_prompt_for_lung_sounds(monkeypatch):
    """lung_sounds / heart_sounds must resolve to AUSCULTATION_VISION_PROMPTS, not blood_panel."""
    findings_json = '{"ok": true}'
    response = _gemini_response(findings_json)

    captured_payloads = {}

    async def fake_post(url, json, **kwargs):
        await asyncio.sleep(0)
        # store payload keyed by the prompt text snippet
        prompt_text = json["contents"][0]["parts"][0]["text"]
        captured_payloads["text"] = prompt_text
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = response
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    from Domain.prompts import AUSCULTATION_VISION_PROMPTS, VISION_PROMPTS

    # --- lung_sounds ---
    client = _make_gemini_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        await client.extract_findings(b"bytes", "image/png", "lung_sounds")

    assert AUSCULTATION_VISION_PROMPTS["lung_sounds"] in captured_payloads["text"], (
        "lung_sounds must use the auscultation-specific prompt, not blood_panel fallback"
    )
    assert VISION_PROMPTS["blood_panel"] not in captured_payloads["text"]

    # --- heart_sounds ---
    client2 = _make_gemini_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        await client2.extract_findings(b"bytes", "image/png", "heart_sounds")

    assert AUSCULTATION_VISION_PROMPTS["heart_sounds"] in captured_payloads["text"], (
        "heart_sounds must use the auscultation-specific prompt, not blood_panel fallback"
    )
    assert VISION_PROMPTS["blood_panel"] not in captured_payloads["text"]


# ---------------------------------------------------------------------------
# extract_tabular tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_tabular_success():
    findings_json = '{"wbc": "normal", "rbc": "low", "confidence": 0.85}'
    response = _gemini_response(findings_json)

    client = _make_gemini_client()
    with _mock_httpx_post(response):
        result = await client.extract_tabular(
            {"wbc": 6.5, "rbc": 3.2, "hemoglobin": 9.1},
            "blood_panel"
        )

    assert result["wbc"] == "normal"
    assert result["confidence"] == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_extract_tabular_sends_data_as_text(monkeypatch):
    """Verify tabular data is serialized into the prompt text."""
    captured = {}

    async def fake_post(url, json, **kwargs):
        await asyncio.sleep(0)
        captured["payload"] = json
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _gemini_response('{"ok": true}')
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    client = _make_gemini_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        await client.extract_tabular({"glucose": 210}, "blood_panel")

    text_part = captured["payload"]["contents"][0]["parts"][0]["text"]
    assert "glucose" in text_part
    assert "210" in text_part
