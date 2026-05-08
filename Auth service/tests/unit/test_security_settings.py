import asyncio
import uuid

import httpx
import pytest
from fastapi import FastAPI


class FakeRepo:
    def __init__(self, model=None):
        self.model = model or FakeModel()
        self.saved = []

    async def get(self):
        await asyncio.sleep(0)
        return self.model

    async def upsert(self, updated_by=None, notification_settings=None, security_settings=None):
        await asyncio.sleep(0)
        self.saved.append({
            "updated_by": updated_by,
            "security_settings": security_settings,
        })
        return self.model


class FakeModel:
    def __init__(self, security_settings=None, updated_at=None, updated_by=None):
        self.security_settings = security_settings
        self.notification_settings = None
        self.updated_at = updated_at
        self.updated_by = updated_by


# ── Route tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_security_requires_admin():
    from presentation.routes.admin import router
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/admin/settings/security", headers={"X-User-Role": "doctor"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_security_requires_admin():
    from presentation.routes.admin import router
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.put(
            "/admin/settings/security",
            json={"audit_log": False},
            headers={"X-User-Role": "doctor"},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_security_returns_defaults_when_empty():
    from presentation.routes.admin import router
    from presentation.dependencies import get_get_security_settings_use_case
    from Application.use_cases.get_security_settings import GetSecuritySettingsUseCase

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_get_security_settings_use_case] = lambda: GetSecuritySettingsUseCase(FakeRepo())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/admin/settings/security", headers={"X-User-Role": "admin"})

    assert r.status_code == 200
    body = r.json()
    assert body["two_factor"] is False
    assert body["session_timeout_minutes"] == 30
    assert body["login_attempt_limit"] == 5
    assert body["audit_log"] is True


@pytest.mark.asyncio
async def test_get_security_returns_stored_values():
    from presentation.routes.admin import router
    from presentation.dependencies import get_get_security_settings_use_case
    from Application.use_cases.get_security_settings import GetSecuritySettingsUseCase

    stored = {
        "two_factor": True,
        "session_timeout_minutes": 60,
        "login_attempt_limit": 3,
        "audit_log": False,
        "password_rules": [{"key": "min8", "label": "Min 8 chars", "checked": True}],
    }
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_get_security_settings_use_case] = lambda: GetSecuritySettingsUseCase(FakeRepo(FakeModel(stored)))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/admin/settings/security", headers={"X-User-Role": "admin"})

    assert r.status_code == 200
    body = r.json()
    assert body["two_factor"] is True
    assert body["session_timeout_minutes"] == 60
    assert body["login_attempt_limit"] == 3
    assert body["audit_log"] is False


@pytest.mark.asyncio
async def test_update_security_partial_update():
    from presentation.routes.admin import router
    from presentation.dependencies import get_upsert_security_settings_use_case
    from Application.use_cases.upsert_security_settings import UpsertSecuritySettingsUseCase

    model = FakeModel({"two_factor": False, "audit_log": True})
    repo = FakeRepo(model)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_upsert_security_settings_use_case] = lambda: UpsertSecuritySettingsUseCase(repo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.put(
            "/admin/settings/security",
            json={"two_factor": True},
            headers={"X-User-Role": "admin"},
        )

    assert r.status_code == 200
    assert repo.saved[0]["security_settings"]["two_factor"] is True


@pytest.mark.asyncio
async def test_update_validates_session_timeout_range():
    from presentation.routes.admin import router
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.put(
            "/admin/settings/security",
            json={"session_timeout_minutes": 1000},
            headers={"X-User-Role": "admin"},
        )
    assert r.status_code == 422
    assert "session_timeout_minutes" in r.json()["detail"]


@pytest.mark.asyncio
async def test_update_validates_login_attempt_limit_range():
    from presentation.routes.admin import router
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.put(
            "/admin/settings/security",
            json={"login_attempt_limit": 0},
            headers={"X-User-Role": "admin"},
        )
    assert r.status_code == 422
    assert "login_attempt_limit" in r.json()["detail"]


# ── Use case unit tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_security_applies_defaults():
    from Application.use_cases.get_security_settings import GetSecuritySettingsUseCase

    repo = FakeRepo(FakeModel())
    uc = GetSecuritySettingsUseCase(repo)
    result = await uc.execute()
    assert result["two_factor"] is False
    assert result["session_timeout_minutes"] == 30
    assert result["audit_log"] is True


@pytest.mark.asyncio
async def test_upsert_security_merges_fields():
    from Application.use_cases.upsert_security_settings import UpsertSecuritySettingsUseCase

    model = FakeModel({"two_factor": False, "audit_log": True})
    repo = FakeRepo(model)
    uc = UpsertSecuritySettingsUseCase(repo)
    await uc.execute(two_factor=True)
    assert repo.saved[0]["security_settings"]["two_factor"] is True


@pytest.mark.asyncio
async def test_upsert_security_saves_password_rules():
    from Application.use_cases.upsert_security_settings import UpsertSecuritySettingsUseCase

    repo = FakeRepo(FakeModel())
    uc = UpsertSecuritySettingsUseCase(repo)
    rules = [{"key": "upper", "label": "Uppercase", "checked": True}]
    await uc.execute(password_rules=rules)
    assert repo.saved[0]["security_settings"]["password_rules"] == rules
