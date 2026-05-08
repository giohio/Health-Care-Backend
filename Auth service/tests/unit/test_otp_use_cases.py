"""Unit tests for OTPRepository, VerifyEmailUseCase, ResendOTPUseCase, and generate_otp."""
import asyncio

import pytest
from Application.resend_otp import ResendOTPUseCase
from Application.verify_email import VerifyEmailUseCase, generate_otp
from Domain.entities.user import User, UserRole
from infrastructure.repositories.otp_repository import OTPRepository, OTP_TTL_SECONDS, RESEND_COOLDOWN_SECONDS

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


async def _yield():
    await asyncio.sleep(0)


class FakeRedis:
    """Minimal in-memory fake for the redis.asyncio.Redis interface used by OTPRepository."""

    def __init__(self):
        self._store: dict[str, str] = {}
        self._pipeline_calls: list[dict] = []

    async def get(self, key: str):
        await _yield()
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        await _yield()
        self._store[key] = value

    async def delete(self, *keys: str):
        await _yield()
        for k in keys:
            self._store.pop(k, None)

    async def exists(self, *keys: str):
        await _yield()
        return sum(1 for k in keys if k in self._store)

    def pipeline(self, transaction: bool = True):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: FakeRedis):
        self._redis = redis
        self._ops: list[tuple] = []

    def set(self, key: str, value: str, ex: int | None = None):
        self._ops.append(("set", key, value, ex))
        return self

    async def execute(self):
        await _yield()
        for op in self._ops:
            if op[0] == "set":
                self._redis._store[op[1]] = op[2]

    async def __aenter__(self):
        await _yield()  # required for async context manager protocol
        return self

    async def __aexit__(self, *_):
        await _yield()  # no-op exit


class FakeUserRepo:
    def __init__(self, user: User | None = None):
        self._user = user
        self.update_calls: list = []

    async def get_by_email(self, _email: str) -> User | None:
        await _yield()
        return self._user

    async def get_by_id(self, _user_id) -> User | None:
        return await self.get_by_email(str(_user_id))

    async def update(self, user_id, **fields):
        await _yield()
        self.update_calls.append((user_id, fields))
        return self._user


class FakePublisher:
    def __init__(self, fail: bool = False):
        self._fail = fail
        self.calls: list[dict] = []

    async def publish(self, **kwargs):
        await _yield()
        self.calls.append(kwargs)
        if self._fail:
            raise RuntimeError("broker down")


# ---------------------------------------------------------------------------
# generate_otp
# ---------------------------------------------------------------------------


def test_generate_otp_is_6_digits():
    otp = generate_otp()
    assert len(otp) == 6
    assert otp.isdigit()


def test_generate_otp_is_different_across_calls():
    samples = {generate_otp() for _ in range(20)}
    # With 1_000_000 possibilities, 20 samples should almost never all be equal
    assert len(samples) > 1


# ---------------------------------------------------------------------------
# OTPRepository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_otp_repository_save_and_get():
    redis = FakeRedis()
    repo = OTPRepository(redis)
    await repo.save("user-1", "123456")
    result = await repo.get("user-1")
    assert result == "123456"


@pytest.mark.asyncio
async def test_otp_repository_get_missing_returns_none():
    repo = OTPRepository(FakeRedis())
    assert await repo.get("nonexistent") is None


@pytest.mark.asyncio
async def test_otp_repository_delete_clears_both_keys():
    redis = FakeRedis()
    repo = OTPRepository(redis)
    await repo.save("user-1", "111111")
    await repo.delete("user-1")
    assert await repo.get("user-1") is None
    assert not await repo.is_in_cooldown("user-1")


@pytest.mark.asyncio
async def test_otp_repository_is_in_cooldown_after_save():
    redis = FakeRedis()
    repo = OTPRepository(redis)
    await repo.save("user-2", "999999")
    assert await repo.is_in_cooldown("user-2") is True


@pytest.mark.asyncio
async def test_otp_repository_not_in_cooldown_before_save():
    repo = OTPRepository(FakeRedis())
    assert await repo.is_in_cooldown("user-new") is False


@pytest.mark.asyncio
async def test_otp_repository_get_bytes_decoded():
    """Simulate redis returning bytes (non-decoded client)."""
    redis = FakeRedis()
    redis._store["email_otp:u1"] = b"654321"  # type: ignore[assignment]
    repo = OTPRepository(redis)
    result = await repo.get("u1")
    assert result == "654321"


# ---------------------------------------------------------------------------
# VerifyEmailUseCase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_email_success():
    user = User("a@b.com", "hashed", UserRole.PATIENT)
    user.is_email_verified = False
    redis = FakeRedis()
    otp_repo = OTPRepository(redis)
    await otp_repo.save(str(user.id), "123456")
    user_repo = FakeUserRepo(user)

    uc = VerifyEmailUseCase(user_repo, otp_repo)
    await uc.execute(email="a@b.com", otp="123456")

    assert len(user_repo.update_calls) == 1
    _uid, fields = user_repo.update_calls[0]
    assert fields == {"is_email_verified": True}
    # OTP removed after success
    assert await otp_repo.get(str(user.id)) is None


@pytest.mark.asyncio
async def test_verify_email_wrong_otp_raises():
    user = User("a@b.com", "hashed", UserRole.PATIENT)
    user.is_email_verified = False
    redis = FakeRedis()
    otp_repo = OTPRepository(redis)
    await otp_repo.save(str(user.id), "123456")

    uc = VerifyEmailUseCase(FakeUserRepo(user), otp_repo)
    with pytest.raises(ValueError, match="Invalid email or OTP"):
        await uc.execute(email="a@b.com", otp="000000")


@pytest.mark.asyncio
async def test_verify_email_expired_otp_raises():
    user = User("a@b.com", "hashed", UserRole.PATIENT)
    user.is_email_verified = False
    # Redis never received OTP → None
    uc = VerifyEmailUseCase(FakeUserRepo(user), OTPRepository(FakeRedis()))
    with pytest.raises(ValueError, match="Invalid email or OTP"):
        await uc.execute(email="a@b.com", otp="123456")


@pytest.mark.asyncio
async def test_verify_email_user_not_found_raises():
    uc = VerifyEmailUseCase(FakeUserRepo(None), OTPRepository(FakeRedis()))
    with pytest.raises(ValueError, match="Invalid email or OTP"):
        await uc.execute(email="missing@b.com", otp="123456")


@pytest.mark.asyncio
async def test_verify_email_already_verified_raises():
    user = User("a@b.com", "hashed", UserRole.PATIENT)
    user.is_email_verified = True
    uc = VerifyEmailUseCase(FakeUserRepo(user), OTPRepository(FakeRedis()))
    with pytest.raises(ValueError, match="already verified"):
        await uc.execute(email="a@b.com", otp="123456")


# ---------------------------------------------------------------------------
# ResendOTPUseCase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resend_otp_success_publishes_event():
    user = User("a@b.com", "hashed", UserRole.PATIENT)
    user.is_email_verified = False
    redis = FakeRedis()
    otp_repo = OTPRepository(redis)
    publisher = FakePublisher()

    uc = ResendOTPUseCase(FakeUserRepo(user), otp_repo, publisher)
    await uc.execute(email="a@b.com")

    assert len(publisher.calls) == 1
    call = publisher.calls[0]
    assert call["routing_key"] == "user.resend_otp"
    assert "otp" in call["message"]
    assert len(call["message"]["otp"]) == 6


@pytest.mark.asyncio
async def test_resend_otp_in_cooldown_raises():
    user = User("a@b.com", "hashed", UserRole.PATIENT)
    user.is_email_verified = False
    redis = FakeRedis()
    otp_repo = OTPRepository(redis)
    await otp_repo.save(str(user.id), "111111")  # sets cooldown key
    publisher = FakePublisher()

    uc = ResendOTPUseCase(FakeUserRepo(user), otp_repo, publisher)
    with pytest.raises(ValueError, match="Please wait"):
        await uc.execute(email="a@b.com")

    assert len(publisher.calls) == 0


@pytest.mark.asyncio
async def test_resend_otp_user_not_found_silently_ignored():
    uc = ResendOTPUseCase(FakeUserRepo(None), OTPRepository(FakeRedis()), FakePublisher())
    # Should not raise
    await uc.execute(email="ghost@example.com")


@pytest.mark.asyncio
async def test_resend_otp_already_verified_silently_ignored():
    user = User("a@b.com", "hashed", UserRole.PATIENT)
    user.is_email_verified = True
    uc = ResendOTPUseCase(FakeUserRepo(user), OTPRepository(FakeRedis()), FakePublisher())
    await uc.execute(email="a@b.com")


@pytest.mark.asyncio
async def test_resend_otp_publisher_failure_does_not_propagate():
    user = User("a@b.com", "hashed", UserRole.PATIENT)
    user.is_email_verified = False
    uc = ResendOTPUseCase(FakeUserRepo(user), OTPRepository(FakeRedis()), FakePublisher(fail=True))
    # Should complete without raising
    await uc.execute(email="a@b.com")
