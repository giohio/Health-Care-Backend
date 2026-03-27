import json
import asyncio
from datetime import date, datetime, time
from uuid import uuid4

import pytest
from Application.use_cases.get_available_slots import GetAvailableSlotsUseCase


class FakeRepo:
    def __init__(self, booked_slots=None, confirmed_count=0):
        self.booked_slots = booked_slots or []
        self.confirmed_count = confirmed_count

    async def get_booked_slots(self, doctor_id, appointment_date):
        await asyncio.sleep(0)
        return self.booked_slots

    async def count_confirmed_on_date(self, doctor_id, appointment_date):
        await asyncio.sleep(0)
        return self.confirmed_count


class FakeDoctorClient:
    def __init__(self, schedule=None, config=None, enhanced_schedule=None):
        self.schedule = schedule
        self.config = config or {"duration_minutes": 30, "buffer_minutes": 5}
        self.enhanced_schedule = enhanced_schedule

    async def get_type_config(self, specialty_id, appointment_type):
        await asyncio.sleep(0)
        return self.config

    async def get_schedule(self, doctor_id):
        await asyncio.sleep(0)
        return self.schedule

    async def get_enhanced_schedule(self, doctor_id, appointment_date):
        await asyncio.sleep(0)
        return self.enhanced_schedule


class FakeCache:
    def __init__(self):
        self.values = {}
        self.setex_calls = []

    async def get(self, key):
        await asyncio.sleep(0)
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        await asyncio.sleep(0)
        self.setex_calls.append((key, ttl, value))
        self.values[key] = json.dumps(value)


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
        slot_duration_minutes = int(
            (
                datetime.combine(date.today(), slot.end_time) - datetime.combine(date.today(), slot.start_time)
            ).total_seconds()
            / 60
        )
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


@pytest.mark.asyncio
async def test_get_available_slots_enhanced_schedule_uses_service_duration():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    enhanced_schedule = {
        "working_hours": [{"start_time": "09:00", "end_time": "10:00", "max_patients": 10}],
        "services": [{"id": "svc-1", "duration_minutes": 20}],
    }
    repo = FakeRepo(booked_slots=[], confirmed_count=1)
    doctor_client = FakeDoctorClient(enhanced_schedule=enhanced_schedule)

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
        service_id="svc-1",
    )

    assert result.error is None
    assert result.duration_minutes == 20
    assert len(result.slots) == 3


@pytest.mark.asyncio
async def test_get_available_slots_enhanced_schedule_respects_max_patients():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    enhanced_schedule = {
        "working_hours": [{"start_time": "09:00", "end_time": "11:00", "max_patients": 2}],
        "services": [],
    }
    repo = FakeRepo(booked_slots=[], confirmed_count=2)
    doctor_client = FakeDoctorClient(enhanced_schedule=enhanced_schedule)

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    assert result.slots == []
    assert result.error == "Doctor has reached maximum patients for this date"


@pytest.mark.asyncio
async def test_get_available_slots_enhanced_schedule_uses_type_config_when_service_missing():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)

    enhanced_schedule = {
        "working_hours": [{"start_time": "09:00", "end_time": "10:30"}],
        "services": [{"id": "svc-1", "duration_minutes": 20}],
    }
    repo = FakeRepo(booked_slots=[], confirmed_count=0)
    doctor_client = FakeDoctorClient(
        enhanced_schedule=enhanced_schedule,
        config={"duration_minutes": 45, "buffer_minutes": 5},
    )

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client)
    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
        service_id="svc-unknown",
    )

    assert result.duration_minutes == 45
    assert len(result.slots) >= 1


def test_extract_working_windows_splits_break_window():
    use_case = GetAvailableSlotsUseCase(appointment_repo=FakeRepo(), doctor_client=FakeDoctorClient())

    windows = use_case._extract_working_windows(
        {
            "start_time": "08:00",
            "end_time": "12:00",
            "break_start": "10:00",
            "break_end": "10:30",
        }
    )

    assert windows == [(time(8, 0), time(10, 0)), (time(10, 30), time(12, 0))]


def test_extract_schedule_window_skips_invalid_and_malformed_items():
    schedule = {
        "working_hours": [
            {"start_time": "invalid", "end_time": "10:00"},
            {"start_time": "09:00"},
            {"start_time": "11:00", "end_time": "12:00"},
        ]
    }

    windows = GetAvailableSlotsUseCase._extract_schedule_window(schedule)

    assert windows == [(time(11, 0), time(12, 0))]


@pytest.mark.asyncio
async def test_get_available_slots_returns_from_cache_without_doctor_client_calls():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)
    cache = FakeCache()
    key = f"slots:{doctor_id}:{appointment_date}:{specialty_id}:general:"
    cache.values[key] = {
        "date": str(appointment_date),
        "doctor_id": str(doctor_id),
        "duration_minutes": 30,
        "slots": [],
        "error": None,
    }

    repo = FakeRepo(booked_slots=[])

    class CountingDoctorClient(FakeDoctorClient):
        def __init__(self):
            super().__init__()
            self.enhanced_calls = 0

        async def get_enhanced_schedule(self, doctor_id, appointment_date):
            self.enhanced_calls += 1
            return await super().get_enhanced_schedule(doctor_id, appointment_date)

    doctor_client = CountingDoctorClient()
    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client, cache=cache)

    result = await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    assert result.duration_minutes == 30
    assert result.slots == []
    assert doctor_client.enhanced_calls == 0


@pytest.mark.asyncio
async def test_get_available_slots_cache_miss_sets_cache_with_expected_ttl():
    doctor_id = uuid4()
    specialty_id = uuid4()
    appointment_date = date(2026, 3, 30)
    cache = FakeCache()

    enhanced_schedule = {
        "working_hours": [{"start_time": "09:00", "end_time": "10:00", "max_patients": 10}],
        "services": [],
    }
    repo = FakeRepo(booked_slots=[], confirmed_count=0)
    doctor_client = FakeDoctorClient(enhanced_schedule=enhanced_schedule)

    use_case = GetAvailableSlotsUseCase(appointment_repo=repo, doctor_client=doctor_client, cache=cache)
    await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type="general",
    )

    assert len(cache.setex_calls) == 1
    key, ttl, _value = cache.setex_calls[0]
    assert key == f"slots:{doctor_id}:{appointment_date}:{specialty_id}:general:"
    assert ttl == 120
