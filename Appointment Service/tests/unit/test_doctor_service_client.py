import asyncio
from datetime import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from infrastructure.clients.doctor_service_client import DoctorServiceClient


class DummyCache:
    async def get(self, _key):
        await asyncio.sleep(0)
        return None

    async def set(self, _key, _value, _ttl=None):
        await asyncio.sleep(0)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._payload


class FakeCircuitBreaker:
    def __init__(self, mode="fetch"):
        self.mode = mode

    async def call(self, fetch, fallback):
        await asyncio.sleep(0)
        if self.mode == "fallback":
            return await fallback()
        return await fetch()


@pytest.mark.asyncio
async def test_get_available_doctors_success(monkeypatch):
    calls = []

    async def fake_get(path, params=None):
        await asyncio.sleep(0)
        calls.append((path, params))
        return FakeResponse([{"doctor_id": str(uuid4())}])

    client = DoctorServiceClient(cache=DummyCache(), base_url="http://doctor")
    client._client = SimpleNamespace(get=fake_get)
    client._cb = FakeCircuitBreaker(mode="fetch")

    result = await client.get_available_doctors(uuid4(), 1, time(9, 30))

    assert isinstance(result, list)
    assert len(result) == 1
    assert calls[0][0] == "/search/available"
    assert calls[0][1]["time"] == "09:30"


@pytest.mark.asyncio
async def test_get_available_doctors_fallback_returns_empty_list():
    client = DoctorServiceClient(cache=DummyCache(), base_url="http://doctor")
    client._cb = FakeCircuitBreaker(mode="fallback")

    result = await client.get_available_doctors(uuid4(), 1, time(9, 30))

    assert result == []


@pytest.mark.asyncio
async def test_get_schedule_fallback_returns_none():
    client = DoctorServiceClient(cache=DummyCache(), base_url="http://doctor")
    client._cb = FakeCircuitBreaker(mode="fallback")

    result = await client.get_schedule(str(uuid4()))

    assert result is None


@pytest.mark.asyncio
async def test_get_schedule_success_path():
    async def fake_get(path, params=None):
        await asyncio.sleep(0)
        return FakeResponse({"items": []})

    client = DoctorServiceClient(cache=DummyCache(), base_url="http://doctor")
    client._client = SimpleNamespace(get=fake_get)
    client._cb = FakeCircuitBreaker(mode="fetch")

    result = await client.get_schedule(str(uuid4()))

    assert result == {"items": []}


@pytest.mark.asyncio
async def test_get_type_config_handles_404_and_errors():
    async def fake_get_404(path, params=None):
        await asyncio.sleep(0)
        return FakeResponse({}, status_code=404)

    async def fake_get_err(path, params=None):
        await asyncio.sleep(0)
        raise RuntimeError("network")

    client = DoctorServiceClient(cache=DummyCache(), base_url="http://doctor")
    client._client = SimpleNamespace(get=fake_get_404)

    not_found = await client.get_type_config(str(uuid4()), "general")
    assert not_found is None

    client._client = SimpleNamespace(get=fake_get_err)
    error_case = await client.get_type_config(str(uuid4()), "general")
    assert error_case is None


@pytest.mark.asyncio
async def test_get_type_config_success_path():
    async def fake_get(path, params=None):
        await asyncio.sleep(0)
        return FakeResponse({"duration_minutes": 30, "amount": 100000})

    client = DoctorServiceClient(cache=DummyCache(), base_url="http://doctor")
    client._client = SimpleNamespace(get=fake_get)

    result = await client.get_type_config(str(uuid4()), "general")

    assert result["duration_minutes"] == 30


@pytest.mark.asyncio
async def test_get_patient_context_and_get_doctor_paths():
    async def fake_get(path, params=None):
        await asyncio.sleep(0)
        if "full-context" in path:
            return FakeResponse({"patient": "ok"})
        return FakeResponse({"doctor": "ok"})

    client = DoctorServiceClient(cache=DummyCache(), base_url="http://doctor")
    client._client = SimpleNamespace(get=fake_get)
    client._cb = FakeCircuitBreaker(mode="fetch")

    patient_ctx = await client.get_patient_full_context(str(uuid4()))
    doctor_ctx = await client.get_doctor(str(uuid4()))

    assert patient_ctx == {"patient": "ok"}
    assert doctor_ctx == {"doctor": "ok"}


@pytest.mark.asyncio
async def test_get_patient_context_and_doctor_fallback_none():
    client = DoctorServiceClient(cache=DummyCache(), base_url="http://doctor")
    client._cb = FakeCircuitBreaker(mode="fallback")

    patient_ctx = await client.get_patient_full_context(str(uuid4()))
    doctor_ctx = await client.get_doctor(str(uuid4()))

    assert patient_ctx is None
    assert doctor_ctx is None
