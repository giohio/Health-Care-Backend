"""
Unit tests for infrastructure/clients/emr_result_client.py

All HTTP calls replaced with Fake async context managers.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.clients.emr_result_client import EmrResultClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client() -> EmrResultClient:
    client = object.__new__(EmrResultClient)
    client._base = "http://emr_result_service:8000"
    client._timeout = 10
    return client


def _make_mock_http_client(get_data=None, raise_for_get=False):
    """Returns (mock_client, mock_response) with configurable GET behavior."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": get_data or {}}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.patch = AsyncMock(return_value=mock_resp)

    return mock_client, mock_resp


# ---------------------------------------------------------------------------
# get_result tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_result_success():
    result_data = {"id": "r-001", "status": "PUBLISHED", "test_name": "Chest X-Ray"}
    mock_client, _ = _make_mock_http_client(get_data=result_data)

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await client.get_result("r-001", token="bearer-token")

    assert result["id"] == "r-001"
    assert result["status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_get_result_sends_authorization_header():
    captured = {}

    async def fake_get(url, headers=None, **kwargs):
        await asyncio.sleep(0)
        captured["url"] = url
        captured["headers"] = headers
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": {"id": "r-001"}}
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = fake_get

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        await client.get_result("r-001", token="test-token-xyz")

    assert captured["headers"]["Authorization"] == "Bearer test-token-xyz"
    assert "/lab-results/r-001" in captured["url"]


# ---------------------------------------------------------------------------
# get_recent_results tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_recent_results_returns_list():
    results_list = [
        {"id": "r-001", "status": "PUBLISHED"},
        {"id": "r-002", "status": "PUBLISHED"},
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"data": results_list}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.get_recent_results("p-001", token="tok", x_user_id="doc-1", x_user_role="doctor", limit=5)

    assert len(results) == 2
    assert results[0]["id"] == "r-001"


@pytest.mark.asyncio
async def test_get_recent_results_passes_query_params():
    captured = {}

    async def fake_get(url, params=None, headers=None, **kwargs):
        await asyncio.sleep(0)
        captured["params"] = params
        captured["headers"] = headers
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": []}
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = fake_get

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        await client.get_recent_results("p-007", token="tok", x_user_id="doc-1", x_user_role="doctor", limit=3)

    assert captured["params"]["patient_id"] == "p-007"
    assert captured["params"]["status"] == "PUBLISHED"
    assert captured["params"]["limit"] == 3
    assert captured["headers"]["X-User-Id"] == "doc-1"
    assert captured["headers"]["X-User-Role"] == "doctor"
    assert captured["headers"]["Authorization"] == "Bearer tok"


# ---------------------------------------------------------------------------
# patch_ai_draft tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_ai_draft_calls_correct_endpoint():
    captured = {}

    async def fake_patch(url, json=None, headers=None, **kwargs):
        await asyncio.sleep(0)
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.patch = fake_patch

    client = _make_client()
    draft = {
        "ai_draft_text": "Draft xray findings",
        "ai_confidence": 0.88,
        "status": "AI_DRAFT",
    }

    with patch("httpx.AsyncClient", return_value=mock_client):
        await client.patch_ai_draft("r-001", draft, x_user_role="service")

    assert "/lab-results/r-001/ai-draft" in captured["url"]
    assert captured["json"]["ai_confidence"] == pytest.approx(0.88)
    assert captured["headers"]["X-User-Role"] == "service"


@pytest.mark.asyncio
async def test_patch_ai_draft_raises_on_http_error():
    import httpx

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock()
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.patch = AsyncMock(return_value=mock_resp)

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await client.patch_ai_draft("r-999", {}, x_user_role="service")


# ---------------------------------------------------------------------------
# get_published_results_for_appointment tests
# ---------------------------------------------------------------------------

def _make_readiness_response(result_entries):
    """Build a fake readiness endpoint JSON dict."""
    return {
        "appointment_id": "appt-001",
        "total_orders": len(result_entries),
        "completed_results": sum(1 for r in result_entries if r.get("status") == "PUBLISHED"),
        "all_ready": all(r.get("status") == "PUBLISHED" for r in result_entries),
        "results": result_entries,
    }


@pytest.mark.asyncio
async def test_get_published_results_returns_list():
    """Fetches published result IDs from readiness, then fetches each result."""
    readiness = _make_readiness_response([
        {"result_id": "r-001", "order_id": "o-001", "status": "PUBLISHED"},
        {"result_id": "r-002", "order_id": "o-002", "status": "PUBLISHED"},
    ])
    result_data = {"id": "r-001", "test_name": "CBC", "status": "PUBLISHED", "ai_draft_text": "normal"}

    call_count = {"n": 0}

    async def fake_get(url, **kwargs):
        await asyncio.sleep(0)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        if "readiness" in url:
            mock_resp.json.return_value = readiness
        else:
            call_count["n"] += 1
            mock_resp.json.return_value = result_data
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = fake_get

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.get_published_results_for_appointment("appt-001")

    assert isinstance(results, list)
    assert call_count["n"] == 2  # 2 per-result fetches


@pytest.mark.asyncio
async def test_get_published_results_filters_non_published():
    """Only PUBLISHED entries in readiness trigger individual fetches."""
    readiness = _make_readiness_response([
        {"result_id": "r-001", "order_id": "o-001", "status": "PUBLISHED"},
        {"result_id": "r-002", "order_id": "o-002", "status": "AI_DRAFT"},  # not published
    ])
    per_result_calls = []

    async def fake_get(url, **kwargs):
        await asyncio.sleep(0)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        if "readiness" in url:
            mock_resp.json.return_value = readiness
        else:
            per_result_calls.append(url)
            mock_resp.json.return_value = {"id": "r-001"}
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = fake_get

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.get_published_results_for_appointment("appt-001")

    # Only r-001 (PUBLISHED) should be fetched
    assert len(per_result_calls) == 1
    assert "r-001" in per_result_calls[0]
    assert "r-002" not in per_result_calls[0]


@pytest.mark.asyncio
async def test_get_published_results_returns_empty_when_no_published():
    """Returns empty list when readiness has no PUBLISHED entries."""
    readiness = _make_readiness_response([
        {"result_id": "r-001", "order_id": "o-001", "status": "AI_DRAFT"},
    ])

    async def fake_get(url, **kwargs):
        await asyncio.sleep(0)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = readiness
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = fake_get

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.get_published_results_for_appointment("appt-001")

    assert results == []


@pytest.mark.asyncio
async def test_get_published_results_skips_failed_individual_fetches():
    """If one per-result GET fails, it is skipped; others are returned."""
    readiness = _make_readiness_response([
        {"result_id": "r-001", "order_id": "o-001", "status": "PUBLISHED"},
        {"result_id": "r-002", "order_id": "o-002", "status": "PUBLISHED"},
    ])

    async def fake_get(url, **kwargs):
        await asyncio.sleep(0)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        if "readiness" in url:
            mock_resp.json.return_value = readiness
        elif "r-002" in url:
            mock_resp.raise_for_status.side_effect = Exception("timeout")
        else:
            mock_resp.json.return_value = {"id": "r-001"}
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = fake_get

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.get_published_results_for_appointment("appt-001")

    # r-001 succeeded, r-002 failed (skipped) — should return 1 result
    assert len(results) == 1
    assert results[0]["id"] == "r-001"


# ---------------------------------------------------------------------------
# patch_holistic_summary tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_holistic_summary_calls_correct_endpoint():
    captured = {}

    async def fake_patch(url, json=None, headers=None, **kwargs):
        await asyncio.sleep(0)
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.patch = fake_patch

    client = _make_client()
    payload = {"ai_holistic_text": "Summary text", "status": "DONE"}

    with patch("httpx.AsyncClient", return_value=mock_client):
        await client.patch_holistic_summary("appt-001", payload, x_user_role="service")

    assert "/appointments/appt-001/lab-summary" in captured["url"]
    assert captured["json"]["status"] == "DONE"
    assert captured["headers"]["X-User-Role"] == "service"


@pytest.mark.asyncio
async def test_patch_holistic_summary_raises_on_http_error():
    import httpx

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.patch = AsyncMock(return_value=mock_resp)

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await client.patch_holistic_summary("appt-001", {"status": "DONE"})

