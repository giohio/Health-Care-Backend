import asyncio
from datetime import date
from uuid import uuid4

import pytest
from Application.event_handlers import user_registered as user_registered_module
from Application.event_handlers.user_registered import UserRegisteredHandler
from Application.use_cases.get_profile import GetProfileUseCase
from Application.use_cases.update_health import UpdateHealthBackgroundUseCase
from Domain.entities.patient_health_background import BloodType, PatientHealthBackground
from Domain.entities.patient_profile import PatientProfile
from uuid_extension import uuid7


class FakeProfileRepo:
    def __init__(self, profile=None):
        self.profile = profile
        self.created = []

    async def get_by_user_id(self, _user_id):
        await asyncio.sleep(0)
        return self.profile

    async def create(self, profile):
        await asyncio.sleep(0)
        self.created.append(profile)
        self.profile = profile
        return profile


class FakeHealthRepo:
    def __init__(self, health=None):
        self.health = health
        self.created = []
        self.updated = []

    async def get_by_patient_id(self, _patient_id):
        await asyncio.sleep(0)
        return self.health

    async def create(self, health):
        await asyncio.sleep(0)
        self.created.append(health)
        self.health = health
        return health

    async def update(self, patient_id, **fields):
        await asyncio.sleep(0)
        self.updated.append((patient_id, fields))
        for key, value in fields.items():
            if hasattr(self.health, key):
                setattr(self.health, key, value)
        return self.health


class FakeInitializeUseCase:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = []

    async def execute(self, user_id):
        await asyncio.sleep(0)
        self.calls.append(user_id)
        if self.should_fail:
            raise RuntimeError("db down")


@pytest.mark.asyncio
async def test_get_profile_returns_fallback_health_when_missing():
    profile = PatientProfile(user_id=uuid4(), full_name="A", date_of_birth=date(1990, 1, 1))
    profile_repo = FakeProfileRepo(profile=profile)
    health_repo = FakeHealthRepo(health=None)
    use_case = GetProfileUseCase(profile_repo=profile_repo, health_repo=health_repo)

    got_profile, health = await use_case.execute(user_id=profile.user_id)

    assert got_profile.id == profile.id
    assert isinstance(health, PatientHealthBackground)
    assert health.patient_id == profile.id


@pytest.mark.asyncio
async def test_update_health_creates_background_when_missing_then_updates():
    profile = PatientProfile(user_id=uuid4(), full_name="A")
    profile_repo = FakeProfileRepo(profile=profile)
    health_repo = FakeHealthRepo(health=None)
    use_case = UpdateHealthBackgroundUseCase(profile_repo=profile_repo, health_repo=health_repo)

    result = await use_case.execute(user_id=profile.user_id, blood_type=BloodType.A, height_cm=170)

    assert result.blood_type == BloodType.A
    assert result.height_cm == 170
    assert len(health_repo.created) == 1
    assert len(health_repo.updated) == 1


@pytest.mark.asyncio
async def test_update_health_updates_existing_without_recreate():
    profile = PatientProfile(user_id=uuid4(), full_name="A")
    existing_health = PatientHealthBackground(patient_id=profile.id, blood_type=BloodType.O)
    profile_repo = FakeProfileRepo(profile=profile)
    health_repo = FakeHealthRepo(health=existing_health)
    use_case = UpdateHealthBackgroundUseCase(profile_repo=profile_repo, health_repo=health_repo)

    result = await use_case.execute(user_id=profile.user_id, weight_kg=65.5)

    assert result.weight_kg == pytest.approx(65.5)
    assert health_repo.created == []
    assert len(health_repo.updated) == 1


@pytest.mark.asyncio
async def test_user_registered_handler_missing_user_id_raises_value_error():
    handler = UserRegisteredHandler(initialize_use_case=FakeInitializeUseCase())

    with pytest.raises(ValueError, match="Missing user_id"):
        await handler.handle({})


@pytest.mark.asyncio
async def test_user_registered_handler_calls_initialize_use_case():
    def fake_uuid7(value):
        return value

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(user_registered_module, "UUID7", fake_uuid7)

    init_use_case = FakeInitializeUseCase()
    handler = UserRegisteredHandler(initialize_use_case=init_use_case)
    user_id = str(uuid7())

    await handler.handle({"user_id": user_id})

    assert len(init_use_case.calls) == 1
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_user_registered_handler_propagates_technical_errors():
    def fake_uuid7(value):
        return value

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(user_registered_module, "UUID7", fake_uuid7)

    handler = UserRegisteredHandler(initialize_use_case=FakeInitializeUseCase(should_fail=True))

    with pytest.raises(RuntimeError, match="db down"):
        await handler.handle({"user_id": str(uuid7())})
    monkeypatch.undo()
