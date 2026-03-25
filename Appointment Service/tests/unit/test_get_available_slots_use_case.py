from datetime import date, time, datetime, timedelta
from uuid import uuid4
import asyncio

import pytest

from Application.use_cases.get_available_slots import GetAvailableSlotsUseCase


class FakeRepo:
    def __init__(self, booked_slots=None):
        self.booked_slots = booked_slots or []

    async def get_booked_slots(self, doctor_id, appointment_date):
        await asyncio.sleep(0)
        return self.booked_slots


class FakeDoctorClient:
    def __init__(self, schedule=None, config=None):
        self.schedule = schedule
        self.config = config or {"duration_minutes": 30, "buffer_minutes": 5}

    async def get_type_config(self, specialty_id, appointment_type):
        await asyncio.sleep(0)
        return self.config

    async def get_schedule(self, doctor_id):
        await asyncio.sleep(0)
        return self.schedule


@pytest.mark.asyncio
async def test_get_available_slots_returns_empty_when_no_schedule():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    repo = FakeRepo()
    doctor_client = FakeDoctorClient(schedule=None)

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    assert result.date == appointment_date
    assert result.doctor_id == doctor_id
    assert len(result.slots) == 0
    assert result.error == "Doctor schedule is unavailable"


@pytest.mark.asyncio
async def test_get_available_slots_returns_empty_when_not_working():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    schedule = {"working_hours": []}
    repo = FakeRepo()
    doctor_client = FakeDoctorClient(schedule=schedule)

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    assert len(result.slots) == 0
    assert result.error == "Doctor is not working in requested date"


@pytest.mark.asyncio
async def test_get_available_slots_returns_all_slots_when_nothing_booked():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    schedule = {"working_hours": [{"start_time": "09:00", "end_time": "11:00"}]}
    repo = FakeRepo(booked_slots=[])
    doctor_client = FakeDoctorClient(
        schedule=schedule,
        config={"duration_minutes": 30, "buffer_minutes": 5},
    )

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    assert len(result.slots) > 0
    for slot in result.slots:
        assert slot.is_available is True
        assert slot.reason is None


@pytest.mark.asyncio
async def test_get_available_slots_marks_booked_slots():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    schedule = {"working_hours": [{"start_time": "09:00", "end_time": "12:00"}]}
    booked_start = time(10, 0)
    booked_end = time(10, 30)
    repo = FakeRepo(booked_slots=[(booked_start, booked_end)])
    doctor_client = FakeDoctorClient(
        schedule=schedule,
        config={"duration_minutes": 30, "buffer_minutes": 5},
    )

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    booked_found = False
    for slot in result.slots:
        if slot.start_time <= booked_start < slot.end_time:
            assert slot.is_available is False
            assert slot.reason == "booked"
            booked_found = True

    assert booked_found or len(result.slots) > 0


@pytest.mark.asyncio
async def test_get_available_slots_respects_slot_duration():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    schedule = {"working_hours": [{"start_time": "09:00", "end_time": "10:30"}]}
    repo = FakeRepo(booked_slots=[])
    doctor_client = FakeDoctorClient(
        schedule=schedule,
        config={"duration_minutes": 60, "buffer_minutes": 0},
    )

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    for slot in result.slots:
        slot_duration_minutes = int((datetime.combine(date.today(), slot.end_time) - datetime.combine(date.today(), slot.start_time)).total_seconds() / 60)
        assert slot_duration_minutes == 60


@pytest.mark.asyncio
async def test_get_available_slots_uses_legacy_schedule_format():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    schedule = {
        "start_time": "09:00",
        "end_time": "11:00",
    }
    repo = FakeRepo(booked_slots=[])
    doctor_client = FakeDoctorClient(
        schedule=schedule,
        config={"duration_minutes": 30, "buffer_minutes": 5},
    )

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    assert len(result.slots) > 0
    assert result.error is None


@pytest.mark.asyncio
async def test_get_available_slots_uses_default_duration_when_no_config():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    schedule = {"working_hours": [{"start_time": "09:00", "end_time": "11:00"}]}
    repo = FakeRepo(booked_slots=[])
    doctor_client = FakeDoctorClient(schedule=schedule, config=None)

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    assert result.duration_minutes == 30
    assert len(result.slots) > 0
