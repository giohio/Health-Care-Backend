import asyncio
from datetime import time
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from presentation.dependencies import (
    get_db,
    get_get_system_config_use_case,
    get_list_users_use_case,
    get_update_user_profile_use_case,
    get_update_user_status_use_case,
    get_upsert_system_config_use_case,
)
from presentation.routes.admin import router


class DummyDb:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        await asyncio.sleep(0)
        self.commits += 1


class DummyGetConfigUC:
    def __init__(self, payload=None):
        self.payload = payload or {
            "clinic_name": "HealthAI Clinic",
            "maintenance_mode": False,
            "default_slot_duration_minutes": 30,
            "max_appointments_per_day": 50,
            "support_email": "support@healthai.vn",
            "working_hours_start": "08:00",
            "working_hours_end": "17:00",
            "updated_at": None,
            "updated_by": None,
        }
        self.calls = 0

    async def execute(self):
        await asyncio.sleep(0)
        self.calls += 1
        return self.payload


class DummyUpsertConfigUC:
    def __init__(self, payload=None, exc=None):
        self.payload = payload or {
            "clinic_name": "HealthAI Clinic",
            "maintenance_mode": True,
            "default_slot_duration_minutes": 30,
            "max_appointments_per_day": 40,
            "support_email": "support@healthai.vn",
            "working_hours_start": "09:00",
            "working_hours_end": "18:00",
            "updated_at": None,
            "updated_by": None,
        }
        self.exc = exc
        self.calls = []

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return self.payload


class DummyListUsersUC:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)
        return {
            "users": [
                {
                    "id": str(uuid4()),
                    "email": "user@healthai.dev",
                    "role": "patient",
                    "is_active": True,
                    "is_email_verified": True,
                    "is_profile_completed": False,
                    "created_at": "2026-04-01T00:00:00+00:00",
                }
            ],
            "total": 1,
            "page": kwargs["page"],
            "limit": kwargs["limit"],
            "total_pages": 1,
        }


class DummyUpdateStatusUC:
    def __init__(self, exc=None):
        self.exc = exc
        self.calls = []

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return {
            "id": str(kwargs["user_id"]),
            "email": "user@healthai.dev",
            "role": "patient",
            "is_active": kwargs["is_active"],
            "is_email_verified": True,
            "is_profile_completed": False,
            "created_at": "2026-04-01T00:00:00+00:00",
        }


class DummyUpdateProfileUC:
    def __init__(self, exc=None):
        self.exc = exc
        self.calls = []

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return {
            "id": str(kwargs["user_id"]),
            "email": kwargs.get("email") or "user@healthai.dev",
            "full_name": kwargs.get("full_name") or "Updated User",
            "role": kwargs.get("role") or "patient",
            "is_active": kwargs.get("is_active") if kwargs.get("is_active") is not None else True,
            "is_email_verified": True,
            "is_profile_completed": False,
            "created_at": "2026-04-01T00:00:00+00:00",
        }


def _build_app():
    app = FastAPI()
    app.include_router(router)
    db_inst = DummyDb()

    async def db_dep():
        yield db_inst

    app.dependency_overrides[get_db] = db_dep
    return app, db_inst


@pytest.mark.asyncio
async def test_get_admin_config_success_with_admin_header():
    app, _ = _build_app()
    uc = DummyGetConfigUC()
    app.dependency_overrides[get_get_system_config_use_case] = lambda: uc

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/admin/config", headers={"X-User-Role": "admin"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["clinic_name"] == "HealthAI Clinic"
    assert uc.calls == 1


@pytest.mark.asyncio
async def test_get_admin_config_rejects_non_admin():
    app, _ = _build_app()
    app.dependency_overrides[get_get_system_config_use_case] = lambda: DummyGetConfigUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/admin/config", headers={"X-User-Role": "patient"})

    assert r.status_code == 403


@pytest.mark.asyncio
async def test_put_admin_config_converts_hhmm_and_commits():
    app, db = _build_app()
    uc = DummyUpsertConfigUC()
    app.dependency_overrides[get_upsert_system_config_use_case] = lambda: uc

    payload = {
        "maintenance_mode": True,
        "working_hours_start": "09:30",
        "working_hours_end": "18:00",
        "default_slot_duration_minutes": 30,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.put(
            "/admin/config",
            json=payload,
            headers={"X-User-Role": "admin", "X-User-Id": str(uuid4())},
        )

    assert r.status_code == 200, r.text
    assert db.commits == 1
    sent = uc.calls[0]
    assert isinstance(sent["working_hours_start"], time)
    assert sent["working_hours_start"].hour == 9
    assert sent["working_hours_start"].minute == 30


@pytest.mark.asyncio
async def test_put_admin_config_maps_validation_error_to_422():
    app, _ = _build_app()
    app.dependency_overrides[get_upsert_system_config_use_case] = lambda: DummyUpsertConfigUC(
        exc=ValueError("working_hours_start must be before working_hours_end")
    )

    payload = {"working_hours_start": "10:00", "working_hours_end": "09:00"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.put(
            "/admin/config",
            json=payload,
            headers={"X-User-Role": "admin", "X-User-Id": str(uuid4())},
        )

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_get_admin_users_returns_envelope():
    app, _ = _build_app()
    uc = DummyListUsersUC()
    app.dependency_overrides[get_list_users_use_case] = lambda: uc

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            "/admin/users",
            params={"role": "patient", "search": "user", "is_active": True, "page": 2, "limit": 10},
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["page"] == 2
    assert body["data"]["limit"] == 10
    assert uc.calls[0]["role"] == "patient"


@pytest.mark.asyncio
async def test_patch_user_status_requires_x_user_id():
    app, _ = _build_app()
    app.dependency_overrides[get_update_user_status_use_case] = lambda: DummyUpdateStatusUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.patch(
            f"/admin/users/{uuid4()}/status",
            json={"is_active": False},
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 401


@pytest.mark.asyncio
async def test_patch_user_status_maps_use_case_errors():
    app, _ = _build_app()
    user_id = uuid4()

    app.dependency_overrides[get_update_user_status_use_case] = lambda: DummyUpdateStatusUC(
        exc=ValueError("Admin cannot change their own active status")
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r_422 = await client.patch(
            f"/admin/users/{user_id}/status",
            json={"is_active": False},
            headers={"X-User-Role": "admin", "X-User-Id": str(uuid4())},
        )
    assert r_422.status_code == 422

    app.dependency_overrides[get_update_user_status_use_case] = lambda: DummyUpdateStatusUC(
        exc=LookupError("User not found")
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r_404 = await client.patch(
            f"/admin/users/{user_id}/status",
            json={"is_active": False},
            headers={"X-User-Role": "admin", "X-User-Id": str(uuid4())},
        )
    assert r_404.status_code == 404


@pytest.mark.asyncio
async def test_patch_user_status_success():
    app, db = _build_app()
    uc = DummyUpdateStatusUC()
    app.dependency_overrides[get_update_user_status_use_case] = lambda: uc

    user_id = uuid4()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.patch(
            f"/admin/users/{user_id}/status",
            json={"is_active": True},
            headers={"X-User-Role": "admin", "X-User-Id": str(uuid4())},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["is_active"] is True
    assert db.commits == 1


@pytest.mark.asyncio
async def test_patch_user_profile_requires_x_user_id():
    app, _ = _build_app()
    app.dependency_overrides[get_update_user_profile_use_case] = lambda: DummyUpdateProfileUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.patch(
            f"/admin/users/{uuid4()}",
            json={"full_name": "New Name"},
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 401


@pytest.mark.asyncio
async def test_patch_user_profile_maps_use_case_errors():
    app, _ = _build_app()
    user_id = uuid4()

    app.dependency_overrides[get_update_user_profile_use_case] = lambda: DummyUpdateProfileUC(
        exc=ValueError("Email already exists")
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r_422 = await client.patch(
            f"/admin/users/{user_id}",
            json={"email": "dup@healthai.dev"},
            headers={"X-User-Role": "admin", "X-User-Id": str(uuid4())},
        )
    assert r_422.status_code == 422

    app.dependency_overrides[get_update_user_profile_use_case] = lambda: DummyUpdateProfileUC(
        exc=LookupError("User not found")
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r_404 = await client.patch(
            f"/admin/users/{user_id}",
            json={"full_name": "New Name"},
            headers={"X-User-Role": "admin", "X-User-Id": str(uuid4())},
        )
    assert r_404.status_code == 404


@pytest.mark.asyncio
async def test_patch_user_profile_success():
    app, db = _build_app()
    uc = DummyUpdateProfileUC()
    app.dependency_overrides[get_update_user_profile_use_case] = lambda: uc

    user_id = uuid4()
    payload = {
        "full_name": "Updated Name",
        "email": "updated@healthai.dev",
        "role": "doctor",
        "is_active": False,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.patch(
            f"/admin/users/{user_id}",
            json=payload,
            headers={"X-User-Role": "admin", "X-User-Id": str(uuid4())},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["email"] == "updated@healthai.dev"
    assert body["data"]["role"] == "doctor"
    assert body["data"]["is_active"] is False
    assert db.commits == 1
