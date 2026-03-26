import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from presentation import dependencies
from presentation.dependencies import (
    get_db,
    get_login_use_case,
    get_logout_use_case,
    get_refresh_token_use_case,
    get_register_service,
    get_user_repository,
)
from presentation.routes.auth import router
from sqlalchemy.exc import IntegrityError


class DummyDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        await asyncio.sleep(0)
        self.commits += 1

    async def rollback(self):
        await asyncio.sleep(0)
        self.rollbacks += 1


class DummyLoginUC:
    def __init__(self, exc=None):
        self.exc = exc

    async def execute(self, **_kwargs):
        await asyncio.sleep(0)
        if self.exc:
            raise self.exc
        return (
            "a",
            "r",
            {
                "id": str(uuid4()),
                "email": "a@b.com",
                "role": "patient",
                "is_active": True,
                "is_email_verified": True,
                "is_profile_completed": False,
            },
        )


class DummyRefreshUC:
    async def execute(self, **_kwargs):
        await asyncio.sleep(0)
        return (
            "a2",
            "r2",
            {
                "id": str(uuid4()),
                "email": "a@b.com",
                "role": "patient",
                "is_active": True,
                "is_email_verified": True,
                "is_profile_completed": False,
            },
        )


class DummyRegisterUC:
    def __init__(self, exc=None):
        self.exc = exc

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        if self.exc:
            raise self.exc
        return {
            "id": str(uuid4()),
            "email": kwargs["email"],
            "role": kwargs.get("role", "patient"),
            "is_active": True,
            "is_email_verified": True,
            "is_profile_completed": False,
        }


class DummyLogoutUC:
    async def execute(self, **_kwargs):
        await asyncio.sleep(0)


def _build_app():
    app = FastAPI()
    app.include_router(router)

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep
    return app


@pytest.mark.asyncio
async def test_get_db_commits_success_and_rolls_back_on_error(monkeypatch):
    db = DummyDb()

    class Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(dependencies, "AsyncSessionLocal", Factory())

    agen = dependencies.get_db()
    yielded = await anext(agen)
    assert yielded is db
    with pytest.raises(StopAsyncIteration):
        await anext(agen)
    assert db.commits == 1

    agen2 = dependencies.get_db()
    await anext(agen2)
    with pytest.raises(RuntimeError):
        await agen2.athrow(RuntimeError("boom"))
    assert db.rollbacks == 1


def test_dependency_factories_smoke(monkeypatch):
    fake_jwt = object()
    monkeypatch.setattr(dependencies, "get_jwt_handler", lambda: fake_jwt)

    assert dependencies.get_password_hasher() is dependencies.get_password_hasher()
    assert dependencies.get_jwt_handler() is dependencies.get_jwt_handler()

    session = object()
    user_repo = dependencies.get_user_repository(session)
    token_repo = dependencies.get_refresh_token_repository(session)
    assert user_repo is not None
    assert token_repo is not None

    assert get_register_service(user_repo, dependencies.get_password_hasher(), SimpleNamespace()) is not None
    assert (
        get_login_use_case(user_repo, token_repo, dependencies.get_password_hasher(), dependencies.get_jwt_handler())
        is not None
    )
    assert get_logout_use_case(token_repo) is not None
    assert get_refresh_token_use_case(user_repo, token_repo, dependencies.get_jwt_handler()) is not None


@pytest.mark.asyncio
async def test_register_staff_forbidden_without_admin_role():
    app = _build_app()
    app.dependency_overrides[get_register_service] = lambda: SimpleNamespace(execute=lambda **kwargs: None)

    payload = {"email": "staff@example.com", "password": "password123", "role": "doctor"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/admin/register-staff", json=payload, headers={"X-User-Role": "patient"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_refresh_without_any_token_returns_401():
    app = _build_app()
    app.dependency_overrides[get_refresh_token_use_case] = lambda: DummyRefreshUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/refresh", json={})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_unexpected_exception_maps_to_500():
    app = _build_app()
    app.dependency_overrides[get_login_use_case] = lambda: DummyLoginUC(exc=RuntimeError("x"))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/login", json={"email": "u@example.com", "password": "password123"})
    assert r.status_code == 500


@pytest.mark.asyncio
async def test_login_invalid_credentials_maps_to_401():
    app = _build_app()
    app.dependency_overrides[get_login_use_case] = lambda: DummyLoginUC(exc=ValueError("invalid"))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/login", json={"email": "u@example.com", "password": "password123"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_register_success_and_bad_request_paths():
    app = _build_app()
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        ok = await client.post("/register", json={"email": "u1@example.com", "password": "password123"})
    assert ok.status_code == 201

    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC(exc=ValueError("bad"))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        bad = await client.post("/register", json={"email": "u1@example.com", "password": "password123"})
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_register_integrity_error_maps_to_409():
    app = _build_app()
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC(
        exc=IntegrityError("insert", {}, RuntimeError("dup"))
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/register", json={"email": "u1@example.com", "password": "password123"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_register_unexpected_exception_maps_to_500():
    app = _build_app()
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC(exc=RuntimeError("boom"))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/register", json={"email": "u1@example.com", "password": "password123"})
    assert r.status_code == 500


@pytest.mark.asyncio
async def test_register_staff_success_for_admin():
    app = _build_app()
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC()

    payload = {"email": "staff@example.com", "password": "password123", "role": "doctor"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/admin/register-staff", json=payload, headers={"X-User-Role": "admin"})
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_register_staff_rejects_invalid_staff_role():
    app = _build_app()
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC()

    payload = {"email": "staff@example.com", "password": "password123", "role": "patient"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/admin/register-staff", json=payload, headers={"X-User-Role": "admin"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_login_refresh_logout_success_paths():
    app = _build_app()
    app.dependency_overrides[get_login_use_case] = lambda: DummyLoginUC()
    app.dependency_overrides[get_refresh_token_use_case] = lambda: DummyRefreshUC()
    app.dependency_overrides[get_logout_use_case] = lambda: DummyLogoutUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        login = await client.post("/login", json={"email": "u@example.com", "password": "password123"})
        assert login.status_code == 200
        assert "access_token" in login.cookies

        refresh = await client.post("/refresh", json={"refresh_token": "rtok"})
        assert refresh.status_code == 200

        logout = await client.post("/logout", json={"refresh_token": "rtok", "logout_all_devices": False})
    assert logout.status_code == 200


@pytest.mark.asyncio
async def test_logout_value_error_maps_to_400():
    app = _build_app()

    class DummyLogoutErrorUC:
        async def execute(self, **_kwargs):
            await asyncio.sleep(0)
            raise ValueError("bad logout")

    app.dependency_overrides[get_logout_use_case] = lambda: DummyLogoutErrorUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/logout", json={"refresh_token": "rtok", "logout_all_devices": False})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_refresh_unexpected_exception_maps_to_500():
    app = _build_app()

    class DummyRefreshErrorUC:
        async def execute(self, **_kwargs):
            await asyncio.sleep(0)
            raise RuntimeError("boom")

    app.dependency_overrides[get_refresh_token_use_case] = lambda: DummyRefreshErrorUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/refresh", json={"refresh_token": "rtok"})
    assert r.status_code == 500


@pytest.mark.asyncio
async def test_register_staff_value_error_maps_to_400():
    app = _build_app()
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC(exc=ValueError("invalid staff data"))

    payload = {"email": "staff@example.com", "password": "password123", "role": "doctor"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/admin/register-staff", json=payload, headers={"X-User-Role": "admin"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_logout_unexpected_exception_maps_to_500():
    app = _build_app()

    class DummyLogoutErrorUC:
        async def execute(self, **_kwargs):
            await asyncio.sleep(0)
            raise RuntimeError("boom")

    app.dependency_overrides[get_logout_use_case] = lambda: DummyLogoutErrorUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/logout", json={"refresh_token": "rtok", "logout_all_devices": False})
    assert r.status_code == 500


@pytest.mark.asyncio
async def test_get_me_unexpected_exception_maps_to_500():
    app = _build_app()

    class DummyUserRepo:
        async def get_by_id(self, _user_id):
            await asyncio.sleep(0)
            raise RuntimeError("db down")

    app.dependency_overrides[get_user_repository] = lambda: DummyUserRepo()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get("/me", headers={"X-User-Id": str(uuid4())})
    assert r.status_code == 500
