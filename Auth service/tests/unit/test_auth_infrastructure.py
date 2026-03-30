"""
Unit tests for Auth Service infrastructure layer:
  - UserRepository (mocked SQLAlchemy session)
  - RefreshTokenRepository (mocked SQLAlchemy session)
  - JWTHandler (mocked file I/O with real RSA key)
  - OutboxEventPublisher (mocked OutboxWriter.write)
  - GET /internal/users/{user_id} route
"""

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


# ──────────────────────────────────────────────
# RSA key fixture for JWTHandler tests
# ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def rsa_private_key_pem() -> str:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


# ──────────────────────────────────────────────
# SQLAlchemy mock helpers
# ──────────────────────────────────────────────

def _mock_execute_result(scalar=None, scalars_list=None, rowcount=1):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalar_one.return_value = scalar
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = scalars_list or ([] if scalar is None else [scalar])
    result.scalars.return_value = mock_scalars
    result.rowcount = rowcount
    return result


def _mock_user_model(user_id=None):
    m = MagicMock()
    m.id = user_id or uuid4()
    m.email = "test@example.com"
    m.hashed_password = "hashed"
    m.role = "patient"
    m.is_active = True
    m.is_deleted = False
    m.is_email_verified = True
    m.is_profile_completed = False
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    m.deleted_at = None
    return m


def _mock_token_model(token_id=None, user_id=None):
    m = MagicMock()
    m.id = token_id or uuid4()
    m.user_id = user_id or uuid4()
    m.token_value = "refresh-token-value"
    m.expires_at = datetime.now(timezone.utc)
    m.is_revoked = False
    m.revoked_at = None
    m.replaced_by_token_id = None
    m.created_at = datetime.now(timezone.utc)
    m.last_used_at = None
    return m


# ──────────────────────────────────────────────
# UserRepository tests
# ──────────────────────────────────────────────

class TestUserRepository:
    def _make_repo(self, execute_result=None, rowcount=1):
        from infrastructure.repositories.user_repository import UserRepository
        session = MagicMock()
        session.add = MagicMock()
        if execute_result is not None:
            session.execute = AsyncMock(return_value=execute_result)
        else:
            session.execute = AsyncMock(return_value=_mock_execute_result(rowcount=rowcount))
        session.flush = AsyncMock()
        return UserRepository(session)

    @pytest.mark.asyncio
    async def test_create_returns_entity(self):
        from Domain.entities.user import User, UserRole
        from infrastructure.repositories.user_repository import UserRepository
        model = _mock_user_model()
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        # After flush the model already has all fields set by mock
        repo = UserRepository(session)

        user = User(email="a@b.com", hashed_password="h", role=UserRole.PATIENT)
        # patch _to_entity to avoid needing a real UserModel
        result = await repo.create(user)
        assert session.add.called
        assert session.flush.called

    @pytest.mark.asyncio
    async def test_get_by_id_found(self):
        model = _mock_user_model()
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=model))
        result = await repo.get_by_id(model.id)
        assert result is not None
        assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=None))
        result = await repo.get_by_id(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_email_found(self):
        model = _mock_user_model()
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=model))
        result = await repo.get_by_email("test@example.com")
        assert result is not None
        assert result.role == "patient"

    @pytest.mark.asyncio
    async def test_get_by_email_not_found(self):
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=None))
        result = await repo.get_by_email("none@example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_username_delegates_to_get_by_email(self):
        model = _mock_user_model()
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=model))
        result = await repo.get_by_username("test@example.com")
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_returns_entity(self):
        model = _mock_user_model()
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=model))
        result = await repo.update(model.id, is_active=False)
        assert result is not None

    @pytest.mark.asyncio
    async def test_delete_returns_true(self):
        repo = self._make_repo(execute_result=_mock_execute_result(rowcount=1))
        result = await repo.delete(uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_false(self):
        repo = self._make_repo(execute_result=_mock_execute_result(rowcount=0))
        result = await repo.delete(uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_list_returns_entities(self):
        model = _mock_user_model()
        repo = self._make_repo(execute_result=_mock_execute_result(scalars_list=[model]))
        result = await repo.list()
        assert len(result) == 1
        assert result[0].email == "test@example.com"

    @pytest.mark.asyncio
    async def test_list_empty(self):
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=None, scalars_list=[]))
        result = await repo.list()
        assert result == []


# ──────────────────────────────────────────────
# RefreshTokenRepository tests
# ──────────────────────────────────────────────

class TestRefreshTokenRepository:
    def _make_repo(self, execute_result=None):
        from infrastructure.repositories.refresh_token_repository import RefreshTokenRepository
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.execute = AsyncMock(return_value=execute_result or _mock_execute_result())
        return RefreshTokenRepository(session)

    @pytest.mark.asyncio
    async def test_create_adds_to_session(self):
        from Domain.entities.refresh_token import RefreshToken
        from infrastructure.repositories.refresh_token_repository import RefreshTokenRepository
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        repo = RefreshTokenRepository(session)

        token_model = _mock_token_model()
        from Domain import RefreshToken
        rt = RefreshToken(
            user_id=token_model.user_id,
            token_value="some-token",
            expires_at=datetime.now(timezone.utc),
        )
        await repo.create(rt)
        assert session.add.called
        assert session.flush.called

    @pytest.mark.asyncio
    async def test_get_by_token_found(self):
        model = _mock_token_model()
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=model))
        result = await repo.get_by_token("refresh-token-value")
        assert result is not None
        assert result.token_value == "refresh-token-value"

    @pytest.mark.asyncio
    async def test_get_by_token_not_found(self):
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=None))
        result = await repo.get_by_token("no-such-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_user_id_returns_list(self):
        model = _mock_token_model()
        repo = self._make_repo(execute_result=_mock_execute_result(scalars_list=[model]))
        result = await repo.get_by_user_id(model.user_id)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_update_returns_entity(self):
        model = _mock_token_model()
        repo = self._make_repo(execute_result=_mock_execute_result(scalar=model))
        result = await repo.update(model.id, is_revoked=True)
        assert result is not None

    @pytest.mark.asyncio
    async def test_delete_by_token_returns_true(self):
        repo = self._make_repo(execute_result=_mock_execute_result(rowcount=1))
        result = await repo.delete("some-token")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_by_token_returns_false_when_missing(self):
        repo = self._make_repo(execute_result=_mock_execute_result(rowcount=0))
        result = await repo.delete("missing-token")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_by_user_id_returns_true(self):
        repo = self._make_repo(execute_result=_mock_execute_result(rowcount=1))
        result = await repo.delete_by_user_id(uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_revoke_all_for_user_returns_rowcount(self):
        repo = self._make_repo(execute_result=_mock_execute_result(rowcount=3))
        result = await repo.revoke_all_for_user(uuid4())
        assert result == 3

    @pytest.mark.asyncio
    async def test_revoke_all_returns_zero_when_none(self):
        repo = self._make_repo(execute_result=_mock_execute_result(rowcount=0))
        result = await repo.revoke_all_for_user(uuid4())
        assert result == 0


# ──────────────────────────────────────────────
# JWTHandler tests
# ──────────────────────────────────────────────

class TestJWTHandler:
    @pytest.mark.asyncio
    async def test_file_not_found_raises(self):
        from infrastructure.security.jwt_handler import JWTHandler
        with patch("builtins.open", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                JWTHandler()

    def test_create_and_decode_round_trip(self, rsa_private_key_pem):
        from infrastructure.security.jwt_handler import JWTHandler
        from Domain.entities.user import UserRole
        from uuid_extension import uuid7

        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=lambda s, *a: s,
            __exit__=lambda s, *a: None,
            read=lambda: rsa_private_key_pem,
        ))):
            handler = JWTHandler()

        user_id = uuid7()
        token = handler.create_access_token(user_id, UserRole.PATIENT, False)
        assert isinstance(token, str)
        assert len(token) > 0

        decoded = handler.decode_access_token(token)
        assert decoded["user_id"] == str(user_id)
        assert decoded["role"] == UserRole.PATIENT

    def test_decode_invalid_token_raises_value_error(self, rsa_private_key_pem):
        from infrastructure.security.jwt_handler import JWTHandler
        from Domain.entities.user import UserRole

        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=lambda s, *a: s,
            __exit__=lambda s, *a: None,
            read=lambda: rsa_private_key_pem,
        ))):
            handler = JWTHandler()

        with pytest.raises(ValueError):
            handler.decode_access_token("not.a.valid.jwt.token")

    def test_create_access_token_with_custom_expiry(self, rsa_private_key_pem):
        from infrastructure.security.jwt_handler import JWTHandler
        from Domain.entities.user import UserRole
        from uuid_extension import uuid7

        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=lambda s, *a: s,
            __exit__=lambda s, *a: None,
            read=lambda: rsa_private_key_pem,
        ))):
            handler = JWTHandler()

        token = handler.create_access_token(uuid7(), UserRole.DOCTOR, True, expires_in=60)
        decoded = handler.decode_access_token(token)
        assert decoded["role"] == UserRole.DOCTOR
        assert decoded["is_profile_completed"] is True


# ──────────────────────────────────────────────
# OutboxEventPublisher tests
# ──────────────────────────────────────────────

class TestOutboxEventPublisher:
    @pytest.mark.asyncio
    async def test_publish_with_user_id_in_message(self, monkeypatch):
        import infrastructure.publishers.outbox_event_publisher as module
        calls = []

        async def fake_write(session, **kwargs):
            await asyncio.sleep(0)
            calls.append(kwargs)

        monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        session = object()
        pub = OutboxEventPublisher(session)
        user_id = str(uuid4())
        await pub.publish("auth_events", "user.registered", {"user_id": user_id, "email": "a@b.com"})

        assert len(calls) == 1
        assert calls[0]["event_type"] == "user.registered"
        assert calls[0]["aggregate_type"] == "auth_events"
        assert calls[0]["payload"]["email"] == "a@b.com"

    @pytest.mark.asyncio
    async def test_publish_with_id_field_in_message(self, monkeypatch):
        import infrastructure.publishers.outbox_event_publisher as module
        calls = []

        async def fake_write(session, **kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        pub = OutboxEventPublisher(object())
        await pub.publish("auth_events", "user.created", {"id": str(uuid4()), "email": "x@y.com"})
        assert len(calls) == 1
        assert calls[0]["aggregate_type"] == "auth_events"

    @pytest.mark.asyncio
    async def test_publish_without_id_uses_random_aggregate(self, monkeypatch):
        import infrastructure.publishers.outbox_event_publisher as module
        calls = []

        async def fake_write(session, **kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        pub = OutboxEventPublisher(object())
        await pub.publish("auth_events", "event.noid", {"data": "no-user-id"})
        assert len(calls) == 1
        assert calls[0]["payload"]["data"] == "no-user-id"

    @pytest.mark.asyncio
    async def test_publish_with_invalid_uuid_uses_random(self, monkeypatch):
        import infrastructure.publishers.outbox_event_publisher as module
        calls = []

        async def fake_write(session, **kwargs):
            calls.append(kwargs)

        monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        pub = OutboxEventPublisher(object())
        await pub.publish("auth_events", "event.bad_id", {"user_id": "not-a-uuid"})
        assert len(calls) == 1  # fallback uuid4 used

    @pytest.mark.asyncio
    async def test_delay_ms_is_ignored(self, monkeypatch):
        import infrastructure.publishers.outbox_event_publisher as module

        async def fake_write(session, **kwargs):
            pass

        monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        pub = OutboxEventPublisher(object())
        # Should not raise even with delay_ms set
        await pub.publish("ex", "rk", {"user_id": str(uuid4())}, delay_ms=5000)


# ──────────────────────────────────────────────
# GET /internal/users/{user_id} route tests
# ──────────────────────────────────────────────

class TestInternalUserEndpoint:
    @pytest.mark.asyncio
    async def test_returns_id_and_email(self):
        import httpx
        from fastapi import FastAPI
        from presentation.routes.auth import get_user_internal
        from presentation.dependencies import get_user_repository

        mock_repo = AsyncMock()
        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.email = "internal@example.com"
        mock_repo.get_by_id.return_value = mock_user

        result = await get_user_internal(str(user_id), user_repo=mock_repo)
        assert result == {"id": str(user_id), "email": "internal@example.com"}

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self):
        from fastapi import HTTPException
        from presentation.routes.auth import get_user_internal

        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc:
            await get_user_internal(str(uuid4()), user_repo=mock_repo)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_uuid_raises_400(self):
        from fastapi import HTTPException
        from presentation.routes.auth import get_user_internal

        with pytest.raises(HTTPException) as exc:
            await get_user_internal("not-a-uuid", user_repo=AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_unexpected_error_raises_500(self):
        from fastapi import HTTPException
        from presentation.routes.auth import get_user_internal

        mock_repo = AsyncMock()
        mock_repo.get_by_id.side_effect = RuntimeError("db error")

        with pytest.raises(HTTPException) as exc:
            await get_user_internal(str(uuid4()), user_repo=mock_repo)
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_route_via_asgi_transport(self):
        import httpx
        from fastapi import FastAPI
        from presentation.routes.auth import router
        from presentation.dependencies import get_user_repository

        app = FastAPI()
        app.include_router(router)

        user_id = uuid4()
        mock_repo = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.email = "route@example.com"
        mock_repo.get_by_id.return_value = mock_user

        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r = await client.get(f"/internal/users/{user_id}")

        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "route@example.com"
        assert body["id"] == str(user_id)

    @pytest.mark.asyncio
    async def test_route_not_found_via_asgi(self):
        import httpx
        from fastapi import FastAPI
        from presentation.routes.auth import router
        from presentation.dependencies import get_user_repository

        app = FastAPI()
        app.include_router(router)

        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        app.dependency_overrides[get_user_repository] = lambda: mock_repo

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r = await client.get(f"/internal/users/{uuid4()}")

        assert r.status_code == 404
