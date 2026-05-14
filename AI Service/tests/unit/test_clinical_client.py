"""
Unit tests for infrastructure/clients/clinical_client.py

All HTTP calls are replaced with Fake async context managers to avoid
real network traffic. Tests cover success path, DOB age calculation,
and the graceful fallback on any exception.
"""

import asyncio
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.clients.clinical_client import ClinicalClient
from Domain.entities import PatientContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client() -> ClinicalClient:
    client = object.__new__(ClinicalClient)
    client._clinical_base = "http://clinical_service:8000"
    client._patient_base  = "http://patient_service:8001"
    client._timeout = 10
    return client


def _mock_httpx_get(response_data: dict):
    """Patch httpx.AsyncClient so .get() returns a fake response."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = response_data

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    return patch("httpx.AsyncClient", return_value=mock_client)


def _mock_httpx_raise(exc):
    """Patch httpx.AsyncClient so .get() raises an exception."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=exc)

    return patch("httpx.AsyncClient", return_value=mock_client)


# ---------------------------------------------------------------------------
# Success path tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_patient_context_success_full_profile():
    dob = date(1980, 6, 15).isoformat()
    response_data = {
        "profile": {
            "full_name": "Nguyễn Văn An",
            "gender": "male",
            "date_of_birth": dob,
        },
        "health_background": {
            "allergies": "Aspirin",
            "chronic_conditions": "Tăng huyết áp",
        },
        "diagnoses": [
            {"diagnosis_name": "Tiểu đường type 2", "status": "active"},
            {"diagnosis_name": "Gout", "status": "resolved"},
        ],
        "medications": [
            {"drug_name": "Metformin", "dosage": "500mg", "status": "active"},
            {"drug_name": "Allopurinol", "dosage": "100mg", "status": "inactive"},
        ],
    }

    client = _make_client()
    with _mock_httpx_get(response_data):
        ctx = await client.get_patient_context("p-001", "u-001", "doctor")

    assert isinstance(ctx, PatientContext)
    assert ctx.patient_id == "p-001"
    assert ctx.full_name == "Nguyễn Văn An"
    assert ctx.gender == "male"
    # Only active diagnoses
    assert "Tiểu đường type 2" in ctx.active_diagnoses
    assert "Gout" not in ctx.active_diagnoses
    # Only active medications
    assert any("Metformin" in m for m in ctx.current_medications)
    assert not any("Allopurinol" in m for m in ctx.current_medications)
    assert ctx.allergies == "Aspirin"
    assert ctx.chronic_conditions == "Tăng huyết áp"


@pytest.mark.asyncio
async def test_get_patient_context_calculates_age_from_dob():
    birth = date.today() - timedelta(days=365 * 45 + 11)  # ~45 years ago
    response_data = {
        "profile": {"full_name": "Test", "date_of_birth": birth.isoformat()},
        "health_background": {},
        "diagnoses": [],
        "medications": [],
    }

    client = _make_client()
    with _mock_httpx_get(response_data):
        ctx = await client.get_patient_context("p-002", "u-002", "patient")

    assert ctx.age == 45


@pytest.mark.asyncio
async def test_get_patient_context_handles_missing_dob():
    response_data = {
        "profile": {"full_name": "Ẩn Danh"},
        "health_background": {},
        "diagnoses": [],
        "medications": [],
    }

    client = _make_client()
    with _mock_httpx_get(response_data):
        ctx = await client.get_patient_context("p-003", "u-003", "patient")

    assert ctx.age is None


@pytest.mark.asyncio
async def test_get_patient_context_empty_response():
    """Empty data dict should not raise — returns defaults."""
    client = _make_client()
    with _mock_httpx_get({}):
        ctx = await client.get_patient_context("p-004", "u-004", "patient")

    assert ctx.full_name == "Patient"
    assert ctx.active_diagnoses == []
    assert ctx.current_medications == []


# ---------------------------------------------------------------------------
# Fallback / error path tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_patient_context_http_error_fallback():
    """Any HTTP error → return minimal PatientContext (never crash pipeline)."""
    import httpx
    client = _make_client()
    with _mock_httpx_raise(httpx.HTTPError("connect failed")):
        ctx = await client.get_patient_context("p-005", "u-005", "doctor")

    assert ctx.patient_id == "p-005"
    assert ctx.full_name == "Patient"
    assert ctx.age is None


@pytest.mark.asyncio
async def test_get_patient_context_json_error_fallback():
    """JSON decode error → return minimal context."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.side_effect = ValueError("bad json")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        ctx = await client.get_patient_context("p-006", "u-006", "patient")

    assert ctx.full_name == "Patient"


@pytest.mark.asyncio
async def test_get_patient_context_passes_correct_headers():
    """X-User-Id and X-User-Role must be forwarded to the clinical service."""
    captured_headers = {}

    async def fake_get(url, headers=None, **kwargs):
        await asyncio.sleep(0)
        captured_headers.update(headers or {})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "profile": {"full_name": "Test"},
            "health_background": {},
            "diagnoses": [],
            "medications": [],
        }
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = fake_get

    client = _make_client()
    with patch("httpx.AsyncClient", return_value=mock_client):
        await client.get_patient_context("p-007", "u-007", "admin")

    assert captured_headers.get("X-User-Id") == "u-007"
    assert captured_headers.get("X-User-Role") == "admin"
