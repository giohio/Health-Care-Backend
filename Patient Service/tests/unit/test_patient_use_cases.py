import asyncio
from datetime import date, datetime
from uuid import uuid4

import pytest
from Application.use_cases.initialize_profile import InitializeProfileUseCase
from Application.use_cases.upload_profile_photo import UploadProfilePhotoUseCase
from Application.use_cases.update_profile import UpdateProfileUseCase
from Domain.entities.patient_profile import Gender, InsuranceInfo, InsuranceType, PatientProfile, VitalSigns


class FakeProfileRepo:
    def __init__(self, existing=None):
        self.existing = existing
        self.created = []
        self.updated = []

    async def get_by_user_id(self, _user_id):
        await asyncio.sleep(0)
        return self.existing

    async def create(self, profile):
        await asyncio.sleep(0)
        self.created.append(profile)
        self.existing = profile
        return profile

    async def update(self, profile_id, **fields):
        await asyncio.sleep(0)
        self.updated.append((profile_id, fields))
        self.existing.update_profile(**fields)
        return self.existing


class FakeHealthRepo:
    def __init__(self):
        self.created = []

    async def create(self, health_bg):
        await asyncio.sleep(0)
        self.created.append(health_bg)
        return health_bg


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_initialize_profile_creates_profile_and_health_when_missing():
    profile_repo = FakeProfileRepo(existing=None)
    health_repo = FakeHealthRepo()
    use_case = InitializeProfileUseCase(profile_repo=profile_repo, health_repo=health_repo)

    created = await use_case.execute(user_id=uuid4())

    assert created is not None
    assert len(profile_repo.created) == 1
    assert len(health_repo.created) == 1
    assert health_repo.created[0].patient_id == created.id


@pytest.mark.asyncio
async def test_initialize_profile_returns_existing_without_creating():
    existing = PatientProfile(user_id=uuid4(), full_name="Existing")
    profile_repo = FakeProfileRepo(existing=existing)
    health_repo = FakeHealthRepo()
    use_case = InitializeProfileUseCase(profile_repo=profile_repo, health_repo=health_repo)

    result = await use_case.execute(user_id=existing.user_id)

    assert result.id == existing.id
    assert profile_repo.created == []
    assert health_repo.created == []


@pytest.mark.asyncio
async def test_update_profile_auto_creates_and_publishes_when_completed():
    profile_repo = FakeProfileRepo(existing=None)
    publisher = FakePublisher()
    use_case = UpdateProfileUseCase(profile_repo=profile_repo, event_publisher=publisher)
    user_id = uuid4()

    result = await use_case.execute(
        user_id=user_id,
        full_name="Patient A",
        date_of_birth=date(1995, 1, 1),
        gender=Gender.MALE,
        address="HCM",
    )

    assert result.full_name == "Patient A"
    assert len(profile_repo.created) == 1
    assert len(profile_repo.updated) == 1
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["routing_key"] == "profile.completed"


@pytest.mark.asyncio
async def test_update_profile_accepts_nested_profile_sections_and_bumps_updated_at():
    existing = PatientProfile(user_id=uuid4(), full_name="Before")
    before = existing.updated_at
    profile_repo = FakeProfileRepo(existing=existing)
    use_case = UpdateProfileUseCase(profile_repo=profile_repo)

    result = await use_case.execute(
        user_id=existing.user_id,
        vital_signs={"height_cm": 172.5, "weight_kg": 68.2, "heart_rate_bpm": 70},
        insurance={
            "type": InsuranceType.BHYT_PUBLIC,
            "card_number": "AB 1234567890",
            "registered_hospital": "Benh vien Bach Mai",
            "expiry_date": date.today(),
        },
    )

    assert isinstance(result.vital_signs, VitalSigns)
    assert result.vital_signs.height_cm == pytest.approx(172.5)
    assert isinstance(result.insurance, InsuranceInfo)
    assert result.insurance.type == InsuranceType.BHYT_PUBLIC
    assert profile_repo.updated[0][1]["updated_at"] >= before


class FakeFileStorage:
    def __init__(self):
        self.calls = []

    def save(self, data: bytes, original_filename: str, subfolder: str = "") -> tuple[str, int]:
        self.calls.append((data, original_filename, subfolder))
        return f"/uploads/{subfolder}/photo.png", len(data)


@pytest.mark.asyncio
async def test_upload_profile_photo_updates_profile_photo_url():
    existing = PatientProfile(user_id=uuid4(), full_name="Patient")
    profile_repo = FakeProfileRepo(existing=existing)
    storage = FakeFileStorage()
    use_case = UploadProfilePhotoUseCase(profile_repo=profile_repo, file_storage=storage)

    result = await use_case.execute(
        user_id=existing.user_id,
        filename="avatar.png",
        content_type="image/png",
        data=b"binary-image-data",
    )

    assert result == "/uploads/profile-photos/photo.png"
    assert storage.calls[0][2] == "profile-photos"
    assert profile_repo.updated[0][1]["profile_photo_url"] == "/uploads/profile-photos/photo.png"


@pytest.mark.asyncio
async def test_upload_profile_photo_rejects_invalid_content_type():
    use_case = UploadProfilePhotoUseCase(profile_repo=FakeProfileRepo(existing=PatientProfile(user_id=uuid4())), file_storage=FakeFileStorage())

    with pytest.raises(ValueError):
        await use_case.execute(
            user_id=uuid4(),
            filename="avatar.txt",
            content_type="text/plain",
            data=b"bad",
        )
