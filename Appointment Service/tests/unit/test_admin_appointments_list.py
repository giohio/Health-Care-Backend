import asyncio
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from presentation.dependencies import get_list_admin_appointments_use_case
from presentation.routes.admin import router


class DummyListFilteredRepo:
    def __init__(self, appointments, total):
        self.appointments = appointments
        self.total = total
        self.calls = []

    async def list_filtered(self, date_from, date_to, status=None, doctor_id=None, page=1, limit=50):
        self.calls.append({"date_from": date_from, "date_to": date_to, "status": status, "doctor_id": doctor_id, "page": page, "limit": limit})
        await asyncio.sleep(0)
        return self.appointments, self.total


def _make_dummy_uc(repo):
    from Application.use_cases.list_admin_appointments import ListAdminAppointmentsUseCase
    return ListAdminAppointmentsUseCase(repo, doctor_client=None)


def _build_app(repo):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_list_admin_appointments_use_case] = lambda: _make_dummy_uc(repo)
    return app


# ── Route-level tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_admin_appointments_requires_admin_role():
    repo = DummyListFilteredRepo([], 0)
    app = _build_app(repo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/admin/appointments", headers={"X-User-Role": "patient"})

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_admin_appointments_returns_paginated_data():
    today = date(2026, 4, 2)
    appts = [
        {
            "id": str(uuid4()),
            "patient_id": str(uuid4()),
            "doctor_id": str(uuid4()),
            "specialty_id": str(uuid4()),
            "appointment_date": str(today),
            "start_time": "09:00:00",
            "end_time": "09:30:00",
            "appointment_type": "consultation",
            "chief_complaint": "headache",
            "status": "confirmed",
            "payment_status": "paid",
            "consultation_fee": 300000.0,
            "queue_number": 1,
            "cancel_reason": None,
            "created_at": "2026-04-01T10:00:00",
        },
    ]
    repo = DummyListFilteredRepo(appts, total=47)
    app = _build_app(repo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/admin/appointments",
            params={"range": "week", "status": "confirmed", "page": "2", "limit": "20"},
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["pagination"]["page"] == 2
    assert body["data"]["pagination"]["limit"] == 20
    assert body["data"]["pagination"]["total"] == 47
    assert body["data"]["pagination"]["total_pages"] == 3
    assert len(body["data"]["appointments"]) == 1
    assert body["data"]["appointments"][0]["status"] == "confirmed"

    call = repo.calls[0]
    assert call["status"] == "confirmed"
    assert call["page"] == 2
    assert call["limit"] == 20


@pytest.mark.asyncio
async def test_list_admin_appointments_resolves_today_range():
    repo = DummyListFilteredRepo([], 0)
    app = _build_app(repo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/admin/appointments",
            params={"range": "today"},
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 200
    call = repo.calls[0]
    assert call["date_from"] == call["date_to"]


@pytest.mark.asyncio
async def test_list_admin_appointments_resolves_quarter_range():
    repo = DummyListFilteredRepo([], 0)
    app = _build_app(repo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/admin/appointments",
            params={"range": "quarter"},
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 200
    call = repo.calls[0]
    assert (call["date_to"] - call["date_from"]).days == 89


@pytest.mark.asyncio
async def test_list_admin_appointments_passes_doctor_id_filter():
    doc_id = str(uuid4())
    repo = DummyListFilteredRepo([], 0)
    app = _build_app(repo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/admin/appointments",
            params={"doctor_id": doc_id},
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 200
    assert repo.calls[0]["doctor_id"] == doc_id


@pytest.mark.asyncio
async def test_list_admin_appointments_defaults_to_page_1_limit_50():
    repo = DummyListFilteredRepo([], 0)
    app = _build_app(repo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/admin/appointments", headers={"X-User-Role": "admin"})

    assert r.status_code == 200
    assert repo.calls[0]["page"] == 1
    assert repo.calls[0]["limit"] == 50


# ── Use case unit tests ────────────────────────────────────────────────────────

class FakeRepo:
    def __init__(self, result):
        self._result = result

    async def list_filtered(self, **kwargs):
        return self._result


@pytest.mark.asyncio
async def test_use_case_paginates_correctly(monkeypatch):
    from Application.use_cases.list_admin_appointments import ListAdminAppointmentsUseCase

    fake_repo = FakeRepo((["appt1", "appt2", "appt3"], 95))
    use_case = ListAdminAppointmentsUseCase(fake_repo, doctor_client=None)

    result = await use_case.execute(page=3, limit=20)

    assert result["data"]["pagination"]["page"] == 3
    assert result["data"]["pagination"]["limit"] == 20
    assert result["data"]["pagination"]["total"] == 95
    assert result["data"]["pagination"]["total_pages"] == 5
    assert result["data"]["appointments"] == ["appt1", "appt2", "appt3"]


@pytest.mark.asyncio
async def test_use_case_total_pages_is_1_when_no_data():
    from Application.use_cases.list_admin_appointments import ListAdminAppointmentsUseCase

    fake_repo = FakeRepo(([], 0))
    use_case = ListAdminAppointmentsUseCase(fake_repo, doctor_client=None)

    result = await use_case.execute()

    assert result["data"]["pagination"]["total_pages"] == 1


@pytest.mark.asyncio
async def test_use_case_returns_empty_list():
    from Application.use_cases.list_admin_appointments import ListAdminAppointmentsUseCase

    fake_repo = FakeRepo(([], 10))
    use_case = ListAdminAppointmentsUseCase(fake_repo, doctor_client=None)

    result = await use_case.execute()

    assert result["data"]["appointments"] == []
    assert result["data"]["pagination"]["total"] == 10
