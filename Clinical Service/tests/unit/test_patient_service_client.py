"""Unit tests for PatientServiceClient — mocks CircuitBreaker.call() directly."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_PATIENT_ID = uuid.uuid4()


def _make_client(cb_return):
    """Create a PatientServiceClient with a mocked circuit breaker."""
    from infrastructure.clients.patient_service_client import PatientServiceClient

    client = PatientServiceClient.__new__(PatientServiceClient)
    client.base_url = "http://fake-patient-svc"
    client._client = AsyncMock()
    client._cb = AsyncMock()
    client._cb.call = AsyncMock(return_value=cb_return)
    return client


class TestPatientServiceClientGetAllergies:
    async def test_returns_allergies_list(self):
        from infrastructure.clients.patient_service_client import PatientServiceClient

        allergies = ["Penicillin", "Sulfa"]
        client = _make_client(allergies)

        result = await client.get_allergies(_PATIENT_ID)

        assert result == allergies
        client._cb.call.assert_awaited_once()

    async def test_returns_empty_list_on_fallback(self):
        client = _make_client([])
        result = await client.get_allergies(_PATIENT_ID)
        assert result == []

    async def test_fetch_logic_parses_allergies_field(self):
        """Verify _fetch closure returns allergies from JSON body."""
        from infrastructure.clients.patient_service_client import PatientServiceClient

        svc = PatientServiceClient.__new__(PatientServiceClient)
        svc.base_url = "http://fake"
        svc._cb = MagicMock()

        # Capture the _fetch closure passed to cb.call
        captured = {}

        async def fake_call(fetch_fn, fallback=None):
            captured["fetch"] = fetch_fn
            captured["fallback"] = fallback
            return await fetch_fn()

        svc._cb.call = fake_call

        # Mock httpx client to return JSON with allergies
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"allergies": ["Aspirin"]}
        svc._client = AsyncMock()
        svc._client.get = AsyncMock(return_value=mock_response)

        result = await svc.get_allergies(_PATIENT_ID)

        assert result == ["Aspirin"]

    async def test_fetch_returns_empty_when_allergies_none(self):
        """If allergies key is missing/null, return empty list."""
        from infrastructure.clients.patient_service_client import PatientServiceClient

        svc = PatientServiceClient.__new__(PatientServiceClient)

        async def fake_call(fetch_fn, fallback=None):
            return await fetch_fn()

        svc._cb = MagicMock()
        svc._cb.call = fake_call

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {}  # no allergies key
        svc._client = AsyncMock()
        svc._client.get = AsyncMock(return_value=mock_response)

        result = await svc.get_allergies(_PATIENT_ID)
        assert result == []

    async def test_fallback_returns_empty_list(self):
        """Directly invoke the fallback closure."""
        from infrastructure.clients.patient_service_client import PatientServiceClient

        svc = PatientServiceClient.__new__(PatientServiceClient)

        captured_fallback = {}

        async def fake_call(fetch_fn, fallback=None):
            captured_fallback["fn"] = fallback
            return await fallback()

        svc._cb = MagicMock()
        svc._cb.call = fake_call
        svc._client = AsyncMock()

        result = await svc.get_allergies(_PATIENT_ID)
        assert result == []


class TestPatientServiceClientGetLatestVitals:
    async def test_returns_vitals_dict(self):
        vitals = {"heart_rate": 72, "blood_pressure": "120/80"}
        client = _make_client(vitals)

        result = await client.get_latest_vitals(_PATIENT_ID)

        assert result == vitals

    async def test_returns_none_on_fallback(self):
        client = _make_client(None)
        result = await client.get_latest_vitals(_PATIENT_ID)
        assert result is None

    async def test_fetch_logic_returns_none_on_404(self):
        """Verify _fetch closure returns None when HTTP 404."""
        from infrastructure.clients.patient_service_client import PatientServiceClient

        svc = PatientServiceClient.__new__(PatientServiceClient)

        async def fake_call(fetch_fn, fallback=None):
            return await fetch_fn()

        svc._cb = MagicMock()
        svc._cb.call = fake_call

        mock_response = MagicMock()
        mock_response.status_code = 404
        svc._client = AsyncMock()
        svc._client.get = AsyncMock(return_value=mock_response)

        result = await svc.get_latest_vitals(_PATIENT_ID)
        assert result is None

    async def test_fetch_logic_returns_json_on_200(self):
        """Verify _fetch closure parses JSON on success."""
        from infrastructure.clients.patient_service_client import PatientServiceClient

        svc = PatientServiceClient.__new__(PatientServiceClient)

        async def fake_call(fetch_fn, fallback=None):
            return await fetch_fn()

        svc._cb = MagicMock()
        svc._cb.call = fake_call

        vitals_data = {"heart_rate": 80}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = vitals_data
        svc._client = AsyncMock()
        svc._client.get = AsyncMock(return_value=mock_response)

        result = await svc.get_latest_vitals(_PATIENT_ID)
        assert result == vitals_data

    async def test_fallback_returns_none(self):
        """Directly invoke the vitals fallback closure."""
        from infrastructure.clients.patient_service_client import PatientServiceClient

        svc = PatientServiceClient.__new__(PatientServiceClient)

        async def fake_call(fetch_fn, fallback=None):
            return await fallback()

        svc._cb = MagicMock()
        svc._cb.call = fake_call
        svc._client = AsyncMock()

        result = await svc.get_latest_vitals(_PATIENT_ID)
        assert result is None
