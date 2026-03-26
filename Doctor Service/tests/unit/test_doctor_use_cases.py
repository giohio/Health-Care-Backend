import asyncio
from uuid import uuid4

import pytest
from Application.dtos import DoctorDTO
from Application.use_cases.register_doctor import RegisterDoctorUseCase
from Application.use_cases.update_doctor_profile import UpdateDoctorProfileUseCase
from Domain.entities.doctor import Doctor
from Domain.exceptions.domain_exceptions import DoctorNotFoundException


class FakeDoctorRepo:
    def __init__(self, doctor=None):
        self.doctor = doctor
        self.saved = []

    async def get_by_id(self, _user_id):
        await asyncio.sleep(0)
        return self.doctor

    async def save(self, doctor):
        await asyncio.sleep(0)
        self.saved.append(doctor)
        self.doctor = doctor
        return doctor


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
async def test_register_doctor_skips_when_doctor_exists():
    existing = Doctor(user_id=uuid4(), full_name="Dr Existing", specialty_id=None)
    repo = FakeDoctorRepo(doctor=existing)
    use_case = RegisterDoctorUseCase(doctor_repo=repo)

    await use_case.execute(user_id=existing.user_id, full_name="Dr New")

    assert repo.saved == []


@pytest.mark.asyncio
async def test_register_doctor_saves_new_doctor_when_missing():
    repo = FakeDoctorRepo(doctor=None)
    use_case = RegisterDoctorUseCase(doctor_repo=repo)
    user_id = uuid4()

    await use_case.execute(user_id=user_id, full_name="Dr New")

    assert len(repo.saved) == 1
    assert repo.saved[0].user_id == user_id
    assert repo.saved[0].full_name == "Dr New"


@pytest.mark.asyncio
async def test_update_doctor_profile_not_found_raises():
    repo = FakeDoctorRepo(doctor=None)
    use_case = UpdateDoctorProfileUseCase(doctor_repo=repo)

    dto = DoctorDTO(user_id=uuid4(), full_name="Dr A")

    with pytest.raises(DoctorNotFoundException):
        await use_case.execute(dto)


@pytest.mark.asyncio
async def test_update_doctor_profile_publishes_profile_completed():
    doctor = Doctor(user_id=uuid4(), full_name="Dr A", specialty_id=None)
    repo = FakeDoctorRepo(doctor=doctor)
    publisher = FakePublisher()
    use_case = UpdateDoctorProfileUseCase(doctor_repo=repo, event_publisher=publisher)

    dto = DoctorDTO(
        user_id=doctor.user_id,
        full_name="Dr Updated",
        specialty_id=uuid4(),
        title="Cardiologist",
        experience_years=8,
        auto_confirm=True,
        confirmation_timeout_minutes=10,
    )

    result = await use_case.execute(dto)

    assert result.full_name == "Dr Updated"
    assert result.experience_years == 8
    assert len(repo.saved) == 1
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["routing_key"] == "profile.completed"
