from uuid import uuid4
import asyncio
from datetime import time

import pytest

from Application.dtos import SpecialtyDTO, ScheduleDTO
from Application.use_cases.list_specialties import ListSpecialtiesUseCase
from Application.use_cases.search_available_doctors import SearchAvailableDoctorsUseCase
from Application.use_cases.set_auto_confirm_settings import SetAutoConfirmSettingsUseCase
from Application.use_cases.save_specialty import SaveSpecialtyUseCase
from Application.use_cases.update_schedule import UpdateScheduleUseCase

from Domain.entities.doctor import Doctor
from Domain.entities.specialty import Specialty
from Domain.entities.doctor_schedule import DoctorSchedule
from Domain.value_objects.day_of_week import DayOfWeek
from Domain.exceptions.domain_exceptions import (
    DoctorNotFoundException,
    SpecialtyAlreadyExistsException,
)


# ============================================================================
# FAKE OBJECTS
# ============================================================================

class FakeSpecialtyRepo:
    def __init__(self, specialties=None):
        self.specialties = specialties or {}
        self.saved = []
        self.by_name_map = {}

    async def list_all(self):
        await asyncio.sleep(0)
        return list(self.specialties.values())

    async def get_by_id(self, specialty_id):
        await asyncio.sleep(0)
        return self.specialties.get(specialty_id)

    async def get_by_name(self, name):
        await asyncio.sleep(0)
        return self.by_name_map.get(name)

    async def save(self, specialty):
        await asyncio.sleep(0)
        self.specialties[specialty.id] = specialty
        self.by_name_map[specialty.name] = specialty
        self.saved.append(specialty)
        return specialty


class FakeDoctorRepo:
    def __init__(self, doctors=None):
        self.doctors = doctors or {}
        self.saved = []

    async def get_by_id(self, doctor_id):
        await asyncio.sleep(0)
        return self.doctors.get(doctor_id)

    async def save(self, doctor):
        await asyncio.sleep(0)
        self.doctors[doctor.user_id] = doctor
        self.saved.append(doctor)
        return doctor

    async def list_by_specialty(self, specialty_id):
        await asyncio.sleep(0)
        return [d for d in self.doctors.values() if d.specialty_id == specialty_id]

    async def search_available(self, specialty_id, day_of_week, time_slot):
        """Mock search that filters by specialty"""
        await asyncio.sleep(0)
        return [d for d in self.doctors.values() if d.specialty_id == specialty_id]


class FakeScheduleRepo:
    def __init__(self):
        self.schedules = {}
        self.saved = []
        self.deleted = []

    async def list_by_doctor(self, doctor_id):
        await asyncio.sleep(0)
        return [s for s in self.schedules.values() if s.doctor_id == doctor_id]

    async def save(self, schedule):
        await asyncio.sleep(0)
        self.schedules[schedule.id] = schedule
        self.saved.append(schedule)
        return schedule

    async def delete(self, schedule_id):
        await asyncio.sleep(0)
        if schedule_id in self.schedules:
            self.deleted.append(self.schedules[schedule_id])
            del self.schedules[schedule_id]

    async def get_available_slots(self, doctor_id, specialty_id, day_of_week):
        await asyncio.sleep(0)
        schedules = await self.list_by_doctor(doctor_id)
        return [s for s in schedules if s.day_of_week == day_of_week]


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


# ============================================================================
# LIST SPECIALTIES USE CASE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_list_specialties_returns_all_specialties():
    """Happy path: Returns all specialties from repo"""
    spec1 = Specialty(id=uuid4(), name="Cardiology", description="Heart specialist")
    spec2 = Specialty(id=uuid4(), name="Neurology", description="Brain specialist")
    repo = FakeSpecialtyRepo(
        specialties={spec1.id: spec1, spec2.id: spec2}
    )
    use_case = ListSpecialtiesUseCase(specialty_repo=repo)

    result = await use_case.execute()

    assert len(result) == 2
    assert any(s.name == "Cardiology" for s in result)
    assert any(s.name == "Neurology" for s in result)


@pytest.mark.asyncio
async def test_list_specialties_returns_empty_when_no_specialties():
    """Edge case: Returns empty list when no specialties exist"""
    repo = FakeSpecialtyRepo(specialties={})
    use_case = ListSpecialtiesUseCase(specialty_repo=repo)

    result = await use_case.execute()

    assert result == []


@pytest.mark.asyncio
async def test_list_specialties_returns_dto_objects():
    """Validation: Returns SpecialtyDTO objects, not domain entities"""
    spec = Specialty(id=uuid4(), name="Orthopedics", description="Bone specialist")
    repo = FakeSpecialtyRepo(specialties={spec.id: spec})
    use_case = ListSpecialtiesUseCase(specialty_repo=repo)

    result = await use_case.execute()

    assert len(result) == 1
    assert result[0].name == "Orthopedics"
    assert isinstance(result[0], SpecialtyDTO)


# ============================================================================
# SEARCH AVAILABLE DOCTORS USE CASE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_search_available_doctors_happy_path():
    """Happy path: Returns doctors with available slots for specialty/day/time"""
    doctor_id = uuid4()
    specialty_id = uuid4()
    doctor = Doctor(
        user_id=doctor_id,
        full_name="Dr. Smith",
        specialty_id=specialty_id,
        auto_confirm=True,
    )

    doctor_repo = FakeDoctorRepo(doctors={doctor_id: doctor})

    use_case = SearchAvailableDoctorsUseCase(
        doctor_repo=doctor_repo,
    )

    result = await use_case.execute(specialty_id, DayOfWeek.MONDAY.value, time(14, 0))

    assert len(result) == 1
    assert result[0].full_name == "Dr. Smith"


@pytest.mark.asyncio
async def test_search_available_doctors_no_results_when_no_doctors():
    """Edge case: Returns empty list when no doctors exist"""
    specialty_id = uuid4()

    doctor_repo = FakeDoctorRepo(doctors={})

    use_case = SearchAvailableDoctorsUseCase(
        doctor_repo=doctor_repo,
    )

    result = await use_case.execute(specialty_id, DayOfWeek.MONDAY.value, time(14, 0))

    assert result == []


@pytest.mark.asyncio
async def test_search_available_doctors_filters_by_specialty():
    """Validation: Filters doctors by requested specialty only"""
    specialty_id = uuid4()
    other_specialty_id = uuid4()

    doctor1 = Doctor(user_id=uuid4(), full_name="Dr. A", specialty_id=specialty_id)
    doctor2 = Doctor(
        user_id=uuid4(), full_name="Dr. B", specialty_id=other_specialty_id
    )

    doctor_repo = FakeDoctorRepo(doctors={doctor1.user_id: doctor1, doctor2.user_id: doctor2})

    use_case = SearchAvailableDoctorsUseCase(
        doctor_repo=doctor_repo,
    )

    result = await use_case.execute(specialty_id, DayOfWeek.MONDAY.value, time(14, 0))

    assert len(result) == 1
    assert result[0].specialty_id == specialty_id


# ============================================================================
# SET AUTO CONFIRM SETTINGS USE CASE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_set_auto_confirm_settings_happy_path():
    """Happy path: Updates auto confirm settings for doctor"""
    doctor_id = uuid4()
    doctor = Doctor(user_id=doctor_id, full_name="Dr. A", specialty_id=None)
    repo = FakeDoctorRepo(doctors={doctor_id: doctor})
    use_case = SetAutoConfirmSettingsUseCase(doctor_repo=repo)

    result = await use_case.execute(
        doctor_id, auto_confirm=True, confirmation_timeout_minutes=10
    )

    assert result.auto_confirm == True
    assert result.confirmation_timeout_minutes == 10
    assert len(repo.saved) == 1
    assert repo.saved[0].auto_confirm == True


@pytest.mark.asyncio
async def test_set_auto_confirm_settings_with_false_value():
    """Happy path: Can disable auto confirm"""
    doctor_id = uuid4()
    doctor = Doctor(user_id=doctor_id, full_name="Dr. A", specialty_id=None, auto_confirm=True)
    repo = FakeDoctorRepo(doctors={doctor_id: doctor})
    use_case = SetAutoConfirmSettingsUseCase(doctor_repo=repo)

    result = await use_case.execute(
        doctor_id, auto_confirm=False, confirmation_timeout_minutes=5
    )

    assert result.auto_confirm == False
    assert result.confirmation_timeout_minutes == 5


@pytest.mark.asyncio
async def test_set_auto_confirm_settings_doctor_not_found():
    """Error case: Raises DoctorNotFoundException when doctor doesn't exist"""
    repo = FakeDoctorRepo(doctors={})
    use_case = SetAutoConfirmSettingsUseCase(doctor_repo=repo)
    doctor_id = uuid4()

    with pytest.raises(DoctorNotFoundException):
        await use_case.execute(doctor_id, auto_confirm=True, confirmation_timeout_minutes=10)


@pytest.mark.asyncio
async def test_set_auto_confirm_settings_negative_timeout_raises_error():
    """Validation: Rejects negative timeout values"""
    doctor_id = uuid4()
    doctor = Doctor(user_id=doctor_id, full_name="Dr. A", specialty_id=None)
    repo = FakeDoctorRepo(doctors={doctor_id: doctor})
    use_case = SetAutoConfirmSettingsUseCase(doctor_repo=repo)

    with pytest.raises(ValueError, match="confirmation_timeout_minutes must be greater than 0"):
        await use_case.execute(
            doctor_id, auto_confirm=True, confirmation_timeout_minutes=-5
        )


@pytest.mark.asyncio
async def test_set_auto_confirm_settings_zero_timeout_raises_error():
    """Validation: Rejects zero timeout values"""
    doctor_id = uuid4()
    doctor = Doctor(user_id=doctor_id, full_name="Dr. A", specialty_id=None)
    repo = FakeDoctorRepo(doctors={doctor_id: doctor})
    use_case = SetAutoConfirmSettingsUseCase(doctor_repo=repo)

    with pytest.raises(ValueError, match="confirmation_timeout_minutes must be greater than 0"):
        await use_case.execute(
            doctor_id, auto_confirm=True, confirmation_timeout_minutes=0
        )


@pytest.mark.asyncio
async def test_set_auto_confirm_settings_minimum_valid_timeout():
    """Validation: Accepts minimum valid timeout (1 minute)"""
    doctor_id = uuid4()
    doctor = Doctor(user_id=doctor_id, full_name="Dr. A", specialty_id=None)
    repo = FakeDoctorRepo(doctors={doctor_id: doctor})
    use_case = SetAutoConfirmSettingsUseCase(doctor_repo=repo)

    result = await use_case.execute(
        doctor_id, auto_confirm=True, confirmation_timeout_minutes=1
    )

    assert result.confirmation_timeout_minutes == 1


# ============================================================================
# SAVE SPECIALTY USE CASE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_save_specialty_creates_new_specialty():
    """Happy path: Creates new specialty with generated ID"""
    repo = FakeSpecialtyRepo()
    use_case = SaveSpecialtyUseCase(specialty_repo=repo)

    dto = SpecialtyDTO(name="Dermatology", description="Skin specialist")

    result = await use_case.execute(dto)

    assert result.name == "Dermatology"
    assert result.id is not None
    assert len(repo.saved) == 1


@pytest.mark.asyncio
async def test_save_specialty_updates_existing_specialty():
    """Happy path: Updates specialty when ID is provided"""
    specialty_id = uuid4()
    existing = Specialty(id=specialty_id, name="Old Name", description="Old desc")
    repo = FakeSpecialtyRepo(
        specialties={specialty_id: existing},
    )
    repo.by_name_map["Old Name"] = existing
    use_case = SaveSpecialtyUseCase(specialty_repo=repo)

    dto = SpecialtyDTO(id=specialty_id, name="New Name", description="New desc")

    result = await use_case.execute(dto)

    assert result.name == "New Name"
    assert result.id == specialty_id
    assert len(repo.saved) == 1


@pytest.mark.asyncio
async def test_save_specialty_rejects_duplicate_name():
    """Error case: Raises exception when specialty name already exists"""
    existing = Specialty(id=uuid4(), name="Cardiology", description="Heart specialist")
    repo = FakeSpecialtyRepo(
        specialties={existing.id: existing},
    )
    repo.by_name_map["Cardiology"] = existing
    use_case = SaveSpecialtyUseCase(specialty_repo=repo)

    # Try to create new specialty with existing name
    new_id = uuid4()
    dto = SpecialtyDTO(id=new_id, name="Cardiology", description="Different desc")

    with pytest.raises(SpecialtyAlreadyExistsException):
        await use_case.execute(dto)


@pytest.mark.asyncio
async def test_save_specialty_allows_same_name_for_update():
    """Edge case: Allows same name when updating existing specialty"""
    specialty_id = uuid4()
    existing = Specialty(id=specialty_id, name="Cardiology", description="Heart specialist")
    repo = FakeSpecialtyRepo(
        specialties={specialty_id: existing},
    )
    repo.by_name_map["Cardiology"] = existing
    use_case = SaveSpecialtyUseCase(specialty_repo=repo)

    # Update with same name should work
    dto = SpecialtyDTO(id=specialty_id, name="Cardiology", description="Updated desc")

    result = await use_case.execute(dto)

    assert result.name == "Cardiology"
    assert result.id == specialty_id


# ============================================================================
# UPDATE SCHEDULE USE CASE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_update_schedule_replaces_doctor_schedule():
    """Happy path: Replaces all schedules for doctor"""
    doctor_id = uuid4()
    doctor = Doctor(user_id=doctor_id, full_name="Dr. A", specialty_id=None)

    doctor_repo = FakeDoctorRepo(doctors={doctor_id: doctor})
    schedule_repo = FakeScheduleRepo()

    # Add existing schedule to be deleted
    old_schedule = DoctorSchedule(
        id=uuid4(),
        doctor_id=doctor_id,
        day_of_week=DayOfWeek.MONDAY.value,
        start_time=time(9, 0),
        end_time=time(17, 0),
        slot_duration_minutes=30,
    )
    schedule_repo.schedules[old_schedule.id] = old_schedule

    use_case = UpdateScheduleUseCase(
        schedule_repo=schedule_repo,
        doctor_repo=doctor_repo,
    )

    # New schedule (different day)
    new_dto = ScheduleDTO(
        doctor_id=doctor_id,
        day_of_week=DayOfWeek.TUESDAY,
        start_time=time(10, 0),
        end_time=time(18, 0),
        slot_duration_minutes=30,
    )

    result = await use_case.execute(doctor_id, [new_dto])

    assert len(result) == 1
    assert result[0].day_of_week == DayOfWeek.TUESDAY
    # Old schedule should be deleted
    assert len(schedule_repo.deleted) == 1
    assert schedule_repo.deleted[0].day_of_week == DayOfWeek.MONDAY.value


@pytest.mark.asyncio
async def test_update_schedule_creates_multiple_schedules():
    """Happy path: Can create multiple schedules at once"""
    doctor_id = uuid4()
    doctor = Doctor(user_id=doctor_id, full_name="Dr. A", specialty_id=None)

    doctor_repo = FakeDoctorRepo(doctors={doctor_id: doctor})
    schedule_repo = FakeScheduleRepo()

    use_case = UpdateScheduleUseCase(
        schedule_repo=schedule_repo,
        doctor_repo=doctor_repo,
    )

    dtos = [
        ScheduleDTO(doctor_id=doctor_id, day_of_week=DayOfWeek.MONDAY, start_time=time(9, 0), end_time=time(17, 0), slot_duration_minutes=30),
        ScheduleDTO(doctor_id=doctor_id, day_of_week=DayOfWeek.TUESDAY, start_time=time(9, 0), end_time=time(17, 0), slot_duration_minutes=30),
        ScheduleDTO(doctor_id=doctor_id, day_of_week=DayOfWeek.WEDNESDAY, start_time=time(10, 0), end_time=time(18, 0), slot_duration_minutes=30),
    ]

    result = await use_case.execute(doctor_id, dtos)

    assert len(result) == 3
    assert len(schedule_repo.saved) == 3


@pytest.mark.asyncio
async def test_update_schedule_doctor_not_found():
    """Error case: Raises exception when doctor doesn't exist"""
    doctor_id = uuid4()

    doctor_repo = FakeDoctorRepo(doctors={})
    schedule_repo = FakeScheduleRepo()

    use_case = UpdateScheduleUseCase(
        schedule_repo=schedule_repo,
        doctor_repo=doctor_repo,
    )

    dto = ScheduleDTO(
        doctor_id=doctor_id,
        day_of_week=DayOfWeek.MONDAY,
        start_time=time(9, 0),
        end_time=time(17, 0),
        slot_duration_minutes=30,
    )

    with pytest.raises(DoctorNotFoundException):
        await use_case.execute(doctor_id, [dto])


@pytest.mark.asyncio
async def test_update_schedule_clears_existing_before_adding_new():
    """Validation: Deletes all existing schedules before adding new ones"""
    doctor_id = uuid4()
    doctor = Doctor(user_id=doctor_id, full_name="Dr. A", specialty_id=None)

    doctor_repo = FakeDoctorRepo(doctors={doctor_id: doctor})
    schedule_repo = FakeScheduleRepo()

    # Add 3 existing schedules
    for i in range(3):
        old_schedule = DoctorSchedule(
            id=uuid4(),
            doctor_id=doctor_id,
            day_of_week=i,
            start_time=time(9, 0),
            end_time=time(17, 0),
            slot_duration_minutes=30,
        )
        schedule_repo.schedules[old_schedule.id] = old_schedule

    use_case = UpdateScheduleUseCase(
        schedule_repo=schedule_repo,
        doctor_repo=doctor_repo,
    )

    # Add 2 new schedules
    new_dtos = [
        ScheduleDTO(doctor_id=doctor_id, day_of_week=DayOfWeek.THURSDAY, start_time=time(9, 0), end_time=time(17, 0), slot_duration_minutes=30),
        ScheduleDTO(doctor_id=doctor_id, day_of_week=DayOfWeek.FRIDAY, start_time=time(9, 0), end_time=time(17, 0), slot_duration_minutes=30),
    ]

    result = await use_case.execute(doctor_id, new_dtos)

    # Should have deleted 3, added 2
    assert len(schedule_repo.deleted) == 3
    assert len(result) == 2
    # Verify only new schedules exist (just check we have 2 new ones)
    remaining = await schedule_repo.list_by_doctor(doctor_id)
    assert len(remaining) == 2
    # Check that result has the right day_of_week values
    result_days = {r.day_of_week for r in result}
    assert DayOfWeek.THURSDAY in result_days or DayOfWeek.THURSDAY.value in result_days or 3 in result_days
    assert DayOfWeek.FRIDAY in result_days or DayOfWeek.FRIDAY.value in result_days or 4 in result_days
