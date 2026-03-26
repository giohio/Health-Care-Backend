import asyncio
from datetime import date
from uuid import uuid4

import pytest
from Application.use_cases.get_profile import GetProfileUseCase
from Application.use_cases.update_health import UpdateHealthBackgroundUseCase
from Application.use_cases.update_profile import UpdateProfileUseCase
from Domain.entities.patient_health_background import PatientHealthBackground
from Domain.entities.patient_profile import Gender, PatientProfile


class FakeProfileRepo:
    def __init__(self, profile=None):
        self.profile = profile
        self.created = []
        self.updated = []

    async def get_by_user_id(self, _user_id):
        await asyncio.sleep(0)
        return self.profile

    async def create(self, profile):
        await asyncio.sleep(0)
        self.created.append(profile)
        self.profile = profile
        return profile

    async def update(self, profile_id, **fields):
        await asyncio.sleep(0)
        self.updated.append((profile_id, fields))
        for key, value in fields.items():
            if hasattr(self.profile, key):
                setattr(self.profile, key, value)
        return self.profile


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


class FakePublisher:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)
        if self.should_fail:
            raise RuntimeError("publish failed")


@pytest.mark.asyncio
async def test_get_profile_creates_blank_profile_when_missing():
    profile_repo = FakeProfileRepo(profile=None)
    health_repo = FakeHealthRepo(health=None)
    use_case = GetProfileUseCase(profile_repo=profile_repo, health_repo=health_repo)

    profile, health = await use_case.execute(uuid4())

    assert profile is not None
    assert len(profile_repo.created) == 1
    assert health.patient_id == profile.id


@pytest.mark.asyncio
async def test_update_profile_not_completed_does_not_publish_event():
    profile = PatientProfile(user_id=uuid4(), full_name=None)
    profile_repo = FakeProfileRepo(profile=profile)
    publisher = FakePublisher()
    use_case = UpdateProfileUseCase(profile_repo=profile_repo, event_publisher=publisher)

    updated = await use_case.execute(user_id=profile.user_id, full_name="Only Name")

    assert updated.full_name == "Only Name"
    assert publisher.calls == []


@pytest.mark.asyncio
async def test_update_profile_publish_failure_is_swallowed():
    profile = PatientProfile(user_id=uuid4(), full_name="A")
    profile_repo = FakeProfileRepo(profile=profile)
    publisher = FakePublisher(should_fail=True)
    use_case = UpdateProfileUseCase(profile_repo=profile_repo, event_publisher=publisher)

    result = await use_case.execute(
        user_id=profile.user_id,
        full_name="Patient A",
        date_of_birth=date(1990, 1, 1),
        gender=Gender.FEMALE,
    )

    assert result.full_name == "Patient A"
    assert len(profile_repo.updated) == 1


@pytest.mark.asyncio
async def test_update_health_ignores_unknown_fields():
    profile = PatientProfile(user_id=uuid4(), full_name="A")
    existing = PatientHealthBackground(patient_id=profile.id)
    profile_repo = FakeProfileRepo(profile=profile)
    health_repo = FakeHealthRepo(health=existing)
    use_case = UpdateHealthBackgroundUseCase(profile_repo=profile_repo, health_repo=health_repo)

    result = await use_case.execute(user_id=profile.user_id, weight_kg=70.0, unknown_field="ignored")

    assert result.weight_kg == pytest.approx(70.0)
    _, fields = health_repo.updated[0]
    assert "unknown_field" not in fields
