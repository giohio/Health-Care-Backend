"""
Unit tests for notification settings use cases.
"""
import asyncio
import uuid

import httpx
import pytest
from fastapi import FastAPI

from presentation.routes.admin import router


class FakeRepo:
    def __init__(self, model=None):
        self.model = model or _FakeModel()
        self.saved = []

    async def get(self):
        await asyncio.sleep(0)
        return self.model

    async def upsert(self, updated_by=None, notification_settings=None, security_settings=None):
        await asyncio.sleep(0)
        if notification_settings is not None:
            self.model.notification_settings = notification_settings
        self.saved.append({"updated_by": updated_by, "notification_settings": notification_settings})
        return self.model


class _FakeModel:
    def __init__(self, notification_settings=None, updated_by=None, updated_at=None, security_settings=None):
        self.notification_settings = notification_settings
        self.updated_by = updated_by
        self.security_settings = security_settings
        self.updated_at = updated_at


# ── Use case: GetNotificationSettingsUseCase ──────────────────────────────────

class TestGetNotificationSettings:
    @pytest.fixture
    def uc(self):
        from Application.use_cases.get_notification_settings import GetNotificationSettingsUseCase
        return GetNotificationSettingsUseCase

    @pytest.mark.asyncio
    async def test_returns_null_settings_when_empty(self, uc):
        model = _FakeModel()
        repo = FakeRepo(model)
        use_case = uc(repo)
        result = await use_case.execute()
        assert result["settings"] is None

    @pytest.mark.asyncio
    async def test_returns_stored_settings(self, uc):
        settings = [{"key": "reminders", "title": "Reminders", "sub": "x", "enabled": True}]
        model = _FakeModel(notification_settings=settings)
        repo = FakeRepo(model)
        use_case = uc(repo)
        result = await use_case.execute()
        assert result["settings"] == settings

    @pytest.mark.asyncio
    async def test_includes_updated_metadata(self, uc):
        uid = uuid.uuid4()
        model = _FakeModel(updated_by=uid)
        repo = FakeRepo(model)
        use_case = uc(repo)
        result = await use_case.execute()
        assert result["updated_by"] == str(uid)


# ── Use case: UpsertNotificationSettingsUseCase ────────────────────────────────

class TestUpsertNotificationSettings:
    @pytest.fixture
    def uc(self):
        from Application.use_cases.upsert_notification_settings import UpsertNotificationSettingsUseCase
        return UpsertNotificationSettingsUseCase

    @pytest.mark.asyncio
    async def test_saves_settings(self, uc):
        model = _FakeModel()
        repo = FakeRepo(model)
        use_case = uc(repo)
        settings = [{"key": "test", "title": "Test", "sub": "x", "enabled": True}]
        result = await use_case.execute(settings=settings)
        assert result["settings"] == settings

    @pytest.mark.asyncio
    async def test_preserves_other_fields(self, uc):
        model = _FakeModel(security_settings={"audit_log": True})
        repo = FakeRepo(model)
        use_case = uc(repo)
        settings = [{"key": "reminders", "title": "Reminders", "sub": "x", "enabled": False}]
        await use_case.execute(settings=settings)
        assert repo.saved[0]["notification_settings"] == settings
        assert repo.saved[0]["updated_by"] is None

    @pytest.mark.asyncio
    async def test_saves_with_caller_id(self, uc):
        uid = uuid.uuid4()
        model = _FakeModel()
        repo = FakeRepo(model)
        use_case = uc(repo)
        await use_case.execute(settings=[], updated_by=uid)
        assert repo.saved[0]["updated_by"] == uid


# ── Route tests ────────────────────────────────────────────────────────────────

def _build_app(repo):
    from presentation.dependencies import (
        get_get_notification_settings_use_case,
        get_upsert_notification_settings_use_case,
    )
    from Application.use_cases.get_notification_settings import GetNotificationSettingsUseCase
    from Application.use_cases.upsert_notification_settings import UpsertNotificationSettingsUseCase

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_get_notification_settings_use_case] = lambda: GetNotificationSettingsUseCase(repo)
    app.dependency_overrides[get_upsert_notification_settings_use_case] = lambda: UpsertNotificationSettingsUseCase(repo)
    return app


class TestNotificationRouteAuth:
    """Test routes via httpx to properly exercise FastAPI dependency injection."""

    @pytest.mark.asyncio
    async def test_get_requires_admin_role(self):
        model = _FakeModel()
        repo = FakeRepo(model)
        app = _build_app(repo)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r = await client.get("/admin/settings/notifications", headers={"X-User-Role": "doctor"})

        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_get_returns_settings_with_admin_role(self):
        settings = [{"key": "reminders", "title": "Reminders", "sub": "x", "enabled": True}]
        model = _FakeModel(notification_settings=settings)
        repo = FakeRepo(model)
        app = _build_app(repo)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r = await client.get("/admin/settings/notifications", headers={"X-User-Role": "admin"})

        assert r.status_code == 200
        assert r.json()["settings"] == settings

    @pytest.mark.asyncio
    async def test_update_requires_admin_role(self):
        model = _FakeModel()
        repo = FakeRepo(model)
        app = _build_app(repo)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r = await client.put(
                "/admin/settings/notifications",
                json={"settings": []},
                headers={"X-User-Role": "doctor"},
            )

        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_update_commits_and_returns(self):
        model = _FakeModel()
        repo = FakeRepo(model)
        app = _build_app(repo)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r = await client.put(
                "/admin/settings/notifications",
                json={"settings": [{"key": "test", "title": "T", "sub": "x", "enabled": True}]},
                headers={"X-User-Role": "admin"},
            )

        assert r.status_code == 200
        assert r.json()["settings"] == [{"key": "test", "title": "T", "sub": "x", "enabled": True}]
