import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from presentation import dependencies
from presentation.dependencies import (
    get_db,
    get_login_use_case,
    get_logout_use_case,
    get_refresh_token_use_case,
    get_register_service,
)
from presentation.routes.auth import router


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
        return "a", "r", {"id": str(uuid4()), "email": "a@b.com", "role": "patient", "is_active": True, "is_email_verified": True, "is_profile_completed": False}


class DummyRefreshUC:
    async def execute(self, **_kwargs):
        await asyncio.sleep(0)
        return "a2", "r2", {"id": str(uuid4()), "email": "a@b.com", "role": "patient", "is_active": True, "is_email_verified": True, "is_profile_completed": False}


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


def test_dependency_factories_smoke():
    assert dependencies.get_password_hasher() is dependencies.get_password_hasher()
    assert dependencies.get_jwt_handler() is dependencies.get_jwt_handler()

    session = object()
    user_repo = dependencies.get_user_repository(session)
    token_repo = dependencies.get_refresh_token_repository(session)
    assert user_repo is not None
    assert token_repo is not None

    assert get_register_service(user_repo, dependencies.get_password_hasher(), SimpleNamespace()) is not None
    assert get_login_use_case(user_repo, token_repo, dependencies.get_password_hasher(), dependencies.get_jwt_handler()) is not None
    assert get_logout_use_case(token_repo) is not None
    assert get_refresh_token_use_case(user_repo, token_repo, dependencies.get_jwt_handler()) is not None


def test_register_staff_forbidden_without_admin_role():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_register_service] = lambda: SimpleNamespace(execute=lambda **kwargs: None)

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep

    client = TestClient(app)
    payload = {"email": "staff@example.com", "password": "password123", "role": "doctor"}
    r = client.post("/admin/register-staff", json=payload, headers={"X-User-Role": "patient"})
    assert r.status_code == 403


def test_refresh_without_any_token_returns_401():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_refresh_token_use_case] = lambda: DummyRefreshUC()

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep

    client = TestClient(app)
    r = client.post("/refresh", json={})
    assert r.status_code == 401


def test_login_unexpected_exception_maps_to_500():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_login_use_case] = lambda: DummyLoginUC(exc=RuntimeError("x"))

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep

    client = TestClient(app)
    r = client.post("/login", json={"email": "u@example.com", "password": "password123"})
    assert r.status_code == 500


def test_login_invalid_credentials_maps_to_401():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_login_use_case] = lambda: DummyLoginUC(exc=ValueError("invalid"))

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep

    client = TestClient(app)
    r = client.post("/login", json={"email": "u@example.com", "password": "password123"})
    assert r.status_code == 401


def test_register_success_and_bad_request_paths():
    app = FastAPI()
    app.include_router(router)

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC()

    client = TestClient(app)
    ok = client.post("/register", json={"email": "u1@example.com", "password": "password123"})
    assert ok.status_code == 201

    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC(exc=ValueError("bad"))
    bad = client.post("/register", json={"email": "u1@example.com", "password": "password123"})
    assert bad.status_code == 400


def test_register_integrity_error_maps_to_409():
    app = FastAPI()
    app.include_router(router)

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC(
        exc=IntegrityError("insert", {}, RuntimeError("dup"))
    )

    client = TestClient(app)
    r = client.post("/register", json={"email": "u1@example.com", "password": "password123"})
    assert r.status_code == 409


def test_register_unexpected_exception_maps_to_500():
    app = FastAPI()
    app.include_router(router)

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC(exc=RuntimeError("boom"))

    client = TestClient(app)
    r = client.post("/register", json={"email": "u1@example.com", "password": "password123"})
    assert r.status_code == 500


def test_register_staff_success_for_admin():
    app = FastAPI()
    app.include_router(router)

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC()

    client = TestClient(app)
    payload = {"email": "staff@example.com", "password": "password123", "role": "doctor"}
    r = client.post("/admin/register-staff", json=payload, headers={"X-User-Role": "admin"})
    assert r.status_code == 201


def test_register_staff_rejects_invalid_staff_role():
    app = FastAPI()
    app.include_router(router)

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_register_service] = lambda: DummyRegisterUC()

    client = TestClient(app)
    payload = {"email": "staff@example.com", "password": "password123", "role": "patient"}
    r = client.post("/admin/register-staff", json=payload, headers={"X-User-Role": "admin"})
    assert r.status_code == 400


def test_login_refresh_logout_success_paths():
    app = FastAPI()
    app.include_router(router)

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_login_use_case] = lambda: DummyLoginUC()
    app.dependency_overrides[get_refresh_token_use_case] = lambda: DummyRefreshUC()
    app.dependency_overrides[get_logout_use_case] = lambda: DummyLogoutUC()

    client = TestClient(app)

    login = client.post("/login", json={"email": "u@example.com", "password": "password123"})
    assert login.status_code == 200
    assert "access_token" in login.cookies

    refresh = client.post("/refresh", json={"refresh_token": "rtok"})
    assert refresh.status_code == 200

    logout = client.post("/logout", json={"refresh_token": "rtok", "logout_all_devices": False})
    assert logout.status_code == 200


def test_logout_value_error_maps_to_400():
    app = FastAPI()
    app.include_router(router)

    class DummyLogoutErrorUC:
        async def execute(self, **_kwargs):
            await asyncio.sleep(0)
            raise ValueError("bad logout")

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_logout_use_case] = lambda: DummyLogoutErrorUC()

    client = TestClient(app)
    r = client.post("/logout", json={"refresh_token": "rtok", "logout_all_devices": False})
    assert r.status_code == 400


def test_refresh_unexpected_exception_maps_to_500():
    app = FastAPI()
    app.include_router(router)

    class DummyRefreshErrorUC:
        async def execute(self, **_kwargs):
            await asyncio.sleep(0)
            raise RuntimeError("boom")

    async def db_dep():
        yield DummyDb()

    app.dependency_overrides[get_db] = db_dep
    app.dependency_overrides[get_refresh_token_use_case] = lambda: DummyRefreshErrorUC()

    client = TestClient(app)
    r = client.post("/refresh", json={"refresh_token": "rtok"})
    assert r.status_code == 500
