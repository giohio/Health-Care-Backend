"""Unit tests for /verify-email and /resend-otp routes, plus can_login domain behaviour."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI
from presentation.dependencies import (
    get_db,
    get_resend_otp_use_case,
    get_verify_email_use_case,
)
from presentation.routes.auth import router


# ---------------------------------------------------------------------------
# Dummy stubs
# ---------------------------------------------------------------------------


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


class DummyVerifyUC:
    def __init__(self, exc=None):
        self.exc = exc
        self.calls: list[dict] = []

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc


class DummyResendUC:
    def __init__(self, exc=None):
        self.exc = exc
        self.calls: list[dict] = []

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc


def _build_app():
    app = FastAPI()
    app.include_router(router)
    db_inst = DummyDb()

    async def db_dep():
        yield db_inst

    app.dependency_overrides[get_db] = db_dep
    return app, db_inst


# ---------------------------------------------------------------------------
# /verify-email
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_email_success_returns_200():
    app, db = _build_app()
    uc = DummyVerifyUC()
    app.dependency_overrides[get_verify_email_use_case] = lambda: uc

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/verify-email", json={"email": "u@example.com", "otp": "123456"})

    assert r.status_code == 200
    assert "verified" in r.json().get("message", "").lower()
    assert len(uc.calls) == 1
    assert uc.calls[0]["email"] == "u@example.com"
    assert uc.calls[0]["otp"] == "123456"
    assert db.commits >= 1


@pytest.mark.asyncio
async def test_verify_email_invalid_otp_returns_400():
    app, _ = _build_app()
    app.dependency_overrides[get_verify_email_use_case] = lambda: DummyVerifyUC(exc=ValueError("Invalid email or OTP"))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/verify-email", json={"email": "u@example.com", "otp": "000000"})

    assert r.status_code == 400
    assert "Invalid" in r.json()["detail"]


@pytest.mark.asyncio
async def test_verify_email_unexpected_error_returns_500():
    app, _ = _build_app()
    app.dependency_overrides[get_verify_email_use_case] = lambda: DummyVerifyUC(exc=RuntimeError("boom"))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/verify-email", json={"email": "u@example.com", "otp": "123456"})

    assert r.status_code == 500


@pytest.mark.asyncio
async def test_verify_email_bad_schema_returns_422():
    """OTP must be exactly 6 numeric digits."""
    app, _ = _build_app()
    app.dependency_overrides[get_verify_email_use_case] = lambda: DummyVerifyUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Too short
        r1 = await client.post("/verify-email", json={"email": "u@example.com", "otp": "123"})
        # Non-numeric
        r2 = await client.post("/verify-email", json={"email": "u@example.com", "otp": "12345a"})
        # Missing otp
        r3 = await client.post("/verify-email", json={"email": "u@example.com"})

    assert r1.status_code == 422
    assert r2.status_code == 422
    assert r3.status_code == 422


# ---------------------------------------------------------------------------
# /resend-otp
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resend_otp_success_returns_200():
    app, db = _build_app()
    uc = DummyResendUC()
    app.dependency_overrides[get_resend_otp_use_case] = lambda: uc

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/resend-otp", json={"email": "u@example.com"})

    assert r.status_code == 200
    body = r.json()
    assert "message" in body
    assert len(uc.calls) == 1
    assert uc.calls[0]["email"] == "u@example.com"
    assert db.commits >= 1


@pytest.mark.asyncio
async def test_resend_otp_cooldown_returns_429():
    app, _ = _build_app()
    app.dependency_overrides[get_resend_otp_use_case] = lambda: DummyResendUC(
        exc=ValueError("Please wait before requesting a new OTP")
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/resend-otp", json={"email": "u@example.com"})

    assert r.status_code == 429
    assert "Please wait" in r.json()["detail"]


@pytest.mark.asyncio
async def test_resend_otp_unexpected_error_returns_500():
    app, _ = _build_app()
    app.dependency_overrides[get_resend_otp_use_case] = lambda: DummyResendUC(exc=RuntimeError("boom"))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/resend-otp", json={"email": "u@example.com"})

    assert r.status_code == 500


@pytest.mark.asyncio
async def test_resend_otp_invalid_email_schema_returns_422():
    app, _ = _build_app()
    app.dependency_overrides[get_resend_otp_use_case] = lambda: DummyResendUC()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.post("/resend-otp", json={"email": "not-an-email"})

    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Domain: User.can_login() with email verification
# ---------------------------------------------------------------------------


def test_can_login_requires_email_verified():
    from Domain.entities.user import User, UserRole

    u = User("a@b.com", "h", UserRole.PATIENT)
    # Fresh user starts with is_email_verified=False
    assert u.is_email_verified is False
    assert u.can_login() is False


def test_can_login_true_when_email_verified():
    from Domain.entities.user import User, UserRole

    u = User("a@b.com", "h", UserRole.PATIENT)
    u.is_email_verified = True
    assert u.can_login() is True


def test_can_login_false_when_inactive_even_if_verified():
    from Domain.entities.user import User, UserRole

    u = User("a@b.com", "h", UserRole.PATIENT)
    u.is_email_verified = True
    u.is_active = False
    assert u.can_login() is False


def test_can_login_false_when_deleted_even_if_verified():
    from Domain.entities.user import User, UserRole

    u = User("a@b.com", "h", UserRole.PATIENT)
    u.is_email_verified = True
    u.is_deleted = True
    assert u.can_login() is False
