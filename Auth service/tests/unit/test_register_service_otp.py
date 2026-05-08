"""Unit tests for RegisterService OTP behaviour."""
import asyncio

import pytest
from Application.register_service import RegisterService
from Domain.entities.user import User, UserRole


async def _yield():
    await asyncio.sleep(0)


class FakeUserRepo:
    def __init__(self, existing=None):
        self._existing = existing
        self.created: list[User] = []
        self.update_calls: list = []

    async def get_by_email(self, _email):
        await _yield()
        return self._existing

    async def create(self, user: User) -> User:
        await _yield()
        self.created.append(user)
        return user

    async def update(self, user_id, **fields):
        await _yield()
        return None


class FakePasswordHasher:
    async def hash(self, plain: str) -> str:
        await _yield()
        return f"hashed:{plain}"

    async def verify(self, plain, hashed):
        await _yield()
        return hashed == f"hashed:{plain}"


class FakePublisher:
    def __init__(self, fail=False):
        self._fail = fail
        self.calls: list[dict] = []

    async def publish(self, **kwargs):
        await _yield()
        self.calls.append(kwargs)
        if self._fail:
            raise RuntimeError("broker down")


class FakeOTPRepo:
    def __init__(self):
        self._store: dict[str, str] = {}
        self.save_calls: list[tuple] = []

    async def save(self, user_id: str, otp: str) -> None:
        await _yield()
        self._store[user_id] = otp
        self.save_calls.append((user_id, otp))

    async def get(self, user_id: str) -> str | None:
        await _yield()
        return self._store.get(user_id)

    async def delete(self, user_id: str) -> None:
        await _yield()
        self._store.pop(user_id, None)

    async def is_in_cooldown(self, user_id: str) -> bool:
        await _yield()
        return False


def _make_service(user_repo=None, publisher=None, otp_repo=None):
    return RegisterService(
        user_repository=user_repo or FakeUserRepo(),
        password_hasher=FakePasswordHasher(),
        event_publisher=publisher or FakePublisher(),
        otp_repository=otp_repo or FakeOTPRepo(),
    )


# ---------------------------------------------------------------------------
# Patient registration — needs OTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_patient_sets_email_not_verified():
    otp_repo = FakeOTPRepo()
    svc = _make_service(otp_repo=otp_repo)
    user = await svc.execute("p@example.com", "Passw0rd!", role=UserRole.PATIENT)

    assert user.is_email_verified is False
    # OTP must be stored for the user
    assert len(otp_repo.save_calls) == 1
    uid, otp = otp_repo.save_calls[0]
    assert uid == str(user.id)
    assert len(otp) == 6 and otp.isdigit()


@pytest.mark.asyncio
async def test_register_patient_publishes_event_with_otp():
    publisher = FakePublisher()
    svc = _make_service(publisher=publisher)
    await svc.execute("p@example.com", "Passw0rd!")

    assert len(publisher.calls) == 1
    msg = publisher.calls[0]["message"]
    assert "otp" in msg
    assert msg["email"] == "p@example.com"
    assert msg["role"] == "patient"


@pytest.mark.asyncio
async def test_register_patient_publisher_failure_does_not_propagate():
    publisher = FakePublisher(fail=True)
    svc = _make_service(publisher=publisher)
    # Should complete without exception
    user = await svc.execute("p@example.com", "Passw0rd!")
    assert user.email == "p@example.com"


# ---------------------------------------------------------------------------
# Staff registration — pre-verified, no OTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_doctor_sets_email_verified():
    otp_repo = FakeOTPRepo()
    svc = _make_service(otp_repo=otp_repo)
    user = await svc.execute("dr@example.com", "Passw0rd!", role=UserRole.DOCTOR)

    assert user.is_email_verified is True
    # No OTP should be generated for staff
    assert len(otp_repo.save_calls) == 0


@pytest.mark.asyncio
async def test_register_admin_sets_email_verified():
    otp_repo = FakeOTPRepo()
    svc = _make_service(otp_repo=otp_repo)
    user = await svc.execute("admin@example.com", "Passw0rd!", role=UserRole.ADMIN)

    assert user.is_email_verified is True
    assert len(otp_repo.save_calls) == 0


@pytest.mark.asyncio
async def test_register_doctor_publishes_event_without_otp():
    publisher = FakePublisher()
    svc = _make_service(publisher=publisher)
    await svc.execute("dr@example.com", "Passw0rd!", role=UserRole.DOCTOR)

    msg = publisher.calls[0]["message"]
    assert "otp" not in msg


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_duplicate_email_raises():
    existing = User("p@example.com", "hashed", UserRole.PATIENT)
    svc = _make_service(user_repo=FakeUserRepo(existing=existing))
    with pytest.raises(ValueError, match="Email already exists"):
        await svc.execute("p@example.com", "Passw0rd!")


@pytest.mark.asyncio
async def test_register_invalid_email_raises():
    svc = _make_service()
    with pytest.raises(ValueError, match="Invalid email format"):
        await svc.execute("not-an-email", "Passw0rd!")


@pytest.mark.asyncio
async def test_register_weak_password_raises():
    svc = _make_service()
    with pytest.raises(ValueError):
        await svc.execute("p@example.com", "123")
