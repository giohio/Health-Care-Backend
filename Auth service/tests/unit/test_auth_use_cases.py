from datetime import datetime, timedelta
import asyncio

import pytest

from Application.log_out import LogOutUseCase
from Application.login_service import LoginUseCase
from Application.refresh_token import RefreshTokenUseCase
from Application.register_service import RegisterService
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
    def __init__(self, should_verify=True):
        self.should_verify = should_verify

    def verify(self, _plain, _hashed):
        return self.should_verify

    def hash(self, plain):
        return f"hashed:{plain}"


class FakeJwtHandler:
    def __init__(self):
        self.calls = []

    def create_access_token(self, **kwargs):
        self.calls.append(kwargs)
        return "access-token"


class FakePublisher:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = []

    async def publish(self, **kwargs):
        await _yield_control()
        self.calls.append(kwargs)
        if self.should_fail:
            raise RuntimeError("publish failed")


@pytest.mark.asyncio
async def test_login_success_creates_access_and_refresh_token():
    user = User("u@example.com", "hashed", UserRole.PATIENT)
    user_repo = FakeUserRepo(user=user)
    token_repo = FakeTokenRepo()
    hasher = FakePasswordHasher(should_verify=True)
    jwt_handler = FakeJwtHandler()

    use_case = LoginUseCase(user_repo=user_repo, token_repo=token_repo, password_hasher=hasher, jwt_handler=jwt_handler)
    access, refresh, returned_user = await use_case.execute("u@example.com", "secret")

    assert access == "access-token"
    assert isinstance(refresh, str) and len(refresh) > 10
    assert returned_user.id == user.id
    assert len(user_repo.update_calls) == 1
    assert len(token_repo.created) == 1
    assert len(jwt_handler.calls) == 1


@pytest.mark.asyncio
async def test_login_invalid_password_raises_and_does_not_issue_tokens():
    user = User("u@example.com", "hashed", UserRole.PATIENT)
    user_repo = FakeUserRepo(user=user)
    token_repo = FakeTokenRepo()
    hasher = FakePasswordHasher(should_verify=False)
    jwt_handler = FakeJwtHandler()

    use_case = LoginUseCase(user_repo=user_repo, token_repo=token_repo, password_hasher=hasher, jwt_handler=jwt_handler)

    with pytest.raises(ValueError, match="Invalid password"):
        await use_case.execute("u@example.com", "wrong")

    assert token_repo.created == []
    assert jwt_handler.calls == []


@pytest.mark.asyncio
async def test_refresh_token_rotates_and_revokes_old_token():
    user = User("u@example.com", "hashed", UserRole.PATIENT)
    old_token = RefreshToken(
        user_id=user.id,
        token_value="old-token",
        expires_at=datetime.now() + timedelta(days=1),
    )
    user_repo = FakeUserRepo(user=user)
    token_repo = FakeTokenRepo(token=old_token)
    jwt_handler = FakeJwtHandler()

    use_case = RefreshTokenUseCase(user_repo=user_repo, token_repo=token_repo, jwt_handler=jwt_handler)
    access, new_refresh, returned_user = await use_case.execute("old-token")

    assert access == "access-token"
    assert new_refresh != "old-token"
    assert returned_user.id == user.id
    assert old_token.is_revoked is True
    assert old_token.replaced_by_token_id is not None
    assert len(token_repo.updated) == 1
    assert len(token_repo.created) == 1


@pytest.mark.asyncio
async def test_logout_all_devices_requires_user_id():
    use_case = LogOutUseCase(token_repository=FakeTokenRepo())

    with pytest.raises(ValueError, match="user_id required"):
        await use_case.execute(refresh_token_value=None, user_id=None, logout_all_devices=True)


@pytest.mark.asyncio
async def test_logout_requires_refresh_token_when_not_all_devices():
    use_case = LogOutUseCase(token_repository=FakeTokenRepo())

    with pytest.raises(ValueError, match="refresh_token required"):
        await use_case.execute(refresh_token_value=None, user_id=None, logout_all_devices=False)


@pytest.mark.asyncio
async def test_logout_valid_token_revokes_and_updates():
    user = User("u@example.com", "hashed", UserRole.PATIENT)
    token = RefreshToken(user_id=user.id, token_value="tok", expires_at=datetime.now() + timedelta(days=1))
    token_repo = FakeTokenRepo(token=token)
    use_case = LogOutUseCase(token_repository=token_repo)

    await use_case.execute(refresh_token_value="tok", user_id=None, logout_all_devices=False)

    assert token.is_revoked is True
    assert len(token_repo.updated) == 1


@pytest.mark.asyncio
async def test_register_service_creates_user_and_publishes_event():
    user_repo = FakeUserRepo(user=None)
    created = []

    async def create_user(user):
        await _yield_control()
        created.append(user)
        return user

    user_repo.create = create_user
    hasher = FakePasswordHasher()
    publisher = FakePublisher()
    use_case = RegisterService(user_repository=user_repo, password_hasher=hasher, event_publisher=publisher)

    result = await use_case.execute("new@example.com", "Valid1!A", role=UserRole.DOCTOR)

    assert result.email == "new@example.com"
    assert result.role == UserRole.DOCTOR
    assert len(created) == 1
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["routing_key"] == "user.registered"


@pytest.mark.asyncio
async def test_register_service_invalid_email_raises():
    user_repo = FakeUserRepo(user=None)
    user_repo.create = lambda _user: None
    use_case = RegisterService(user_repository=user_repo, password_hasher=FakePasswordHasher(), event_publisher=FakePublisher())

    with pytest.raises(ValueError, match="Invalid email format"):
        await use_case.execute("not-an-email", "Valid1!A")


@pytest.mark.asyncio
async def test_register_service_existing_email_raises():
    existing_user = User("dup@example.com", "hashed", UserRole.PATIENT)
    user_repo = FakeUserRepo(user=existing_user)
    use_case = RegisterService(user_repository=user_repo, password_hasher=FakePasswordHasher(), event_publisher=FakePublisher())

    with pytest.raises(ValueError, match="Email already exists"):
        await use_case.execute("dup@example.com", "Valid1!A")


@pytest.mark.asyncio
async def test_register_service_publish_failure_is_swallowed():
    user_repo = FakeUserRepo(user=None)

    async def create_user(user):
        await _yield_control()
        return user

    user_repo.create = create_user
    use_case = RegisterService(
        user_repository=user_repo,
        password_hasher=FakePasswordHasher(),
        event_publisher=FakePublisher(should_fail=True),
    )

    result = await use_case.execute("safe@example.com", "Valid1!A")
    assert result.email == "safe@example.com"
