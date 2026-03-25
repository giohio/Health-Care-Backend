from datetime import datetime, timedelta
import asyncio

import pytest

from Application.log_out import LogOutUseCase
from Application.login_service import LoginUseCase
from Application.refresh_token import RefreshTokenUseCase
from Domain.entities.refresh_token import RefreshToken
from Domain.entities.user import User, UserRole


async def _yield_control():
    await asyncio.sleep(0)


class FakeUserRepo:
    def __init__(self, user=None):
        self.user = user
        self.update_calls = []

    async def get_by_email(self, _email):
        await _yield_control()
        return self.user

    async def get_by_id(self, _user_id):
        await _yield_control()
        return self.user

    async def update(self, user_id, **fields):
        await _yield_control()
        self.update_calls.append((user_id, fields))
        return self.user


class FakeTokenRepo:
    def __init__(self, token=None):
        self.token = token
        self.created = []
        self.updated = []
        self.revoked_all = []

    async def create(self, refresh_token):
        await _yield_control()
        self.created.append(refresh_token)
        return refresh_token

    async def get_by_token(self, _token_value):
        await _yield_control()
        return self.token

    async def update(self, token_id, **fields):
        await _yield_control()
        self.updated.append((token_id, fields))
        return self.token

    async def revoke_all_for_user(self, user_id):
        await _yield_control()
        self.revoked_all.append(user_id)
        return 1


class FakePasswordHasher:
    def verify(self, _plain, _hashed):
        return True


class FakeJwtHandler:
    def create_access_token(self, **_kwargs):
        return "access-token"


@pytest.mark.asyncio
async def test_login_user_not_found_raises_value_error():
    use_case = LoginUseCase(
        user_repo=FakeUserRepo(user=None),
        token_repo=FakeTokenRepo(),
        password_hasher=FakePasswordHasher(),
        jwt_handler=FakeJwtHandler(),
    )

    with pytest.raises(ValueError, match="User not found"):
        await use_case.execute("missing@example.com", "secret")


@pytest.mark.asyncio
async def test_login_inactive_user_raises_and_skips_token_creation():
    user = User("u@example.com", "hashed", UserRole.PATIENT)
    user.is_active = False
    token_repo = FakeTokenRepo()
    use_case = LoginUseCase(
        user_repo=FakeUserRepo(user=user),
        token_repo=token_repo,
        password_hasher=FakePasswordHasher(),
        jwt_handler=FakeJwtHandler(),
    )

    with pytest.raises(ValueError, match="User is not active"):
        await use_case.execute("u@example.com", "secret")

    assert token_repo.created == []


@pytest.mark.asyncio
async def test_refresh_token_invalid_or_expired_raises_value_error():
    expired_token = RefreshToken(
        user_id=User("u@example.com", "hashed", UserRole.PATIENT).id,
        token_value="expired-token",
        expires_at=datetime.now() - timedelta(minutes=1),
    )
    use_case = RefreshTokenUseCase(
        user_repo=FakeUserRepo(),
        token_repo=FakeTokenRepo(token=expired_token),
        jwt_handler=FakeJwtHandler(),
    )

    with pytest.raises(ValueError, match="Invalid or expired refresh token"):
        await use_case.execute("expired-token")


@pytest.mark.asyncio
async def test_logout_all_devices_revokes_all_tokens_for_user():
    user = User("u@example.com", "hashed", UserRole.PATIENT)
    token_repo = FakeTokenRepo()
    use_case = LogOutUseCase(token_repository=token_repo)

    await use_case.execute(refresh_token_value=None, user_id=user.id, logout_all_devices=True)

    assert len(token_repo.revoked_all) == 1
