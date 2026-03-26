from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from Application.use_cases.get_availability import GetAvailabilityUseCase
from Application.use_cases.get_enhanced_schedule import GetEnhancedScheduleUseCase
from Application.use_cases.list_ratings import ListRatingsUseCase
from Application.use_cases.manage_day_off import AddDayOffUseCase, RemoveDayOffUseCase
from Application.use_cases.manage_service_offerings import (
    AddServiceOfferingUseCase,
    DeactivateServiceOfferingUseCase,
    ListServiceOfferingsUseCase,
    UpdateServiceOfferingUseCase,
)
from Application.use_cases.set_availability import SetAvailabilityUseCase
from Application.use_cases.submit_rating import SubmitRatingUseCase


@pytest.mark.asyncio
async def test_get_enhanced_schedule_includes_breaks_services_and_day_off_flag():
    doctor_id = uuid4()
    target_date = date(2026, 3, 30)

    availability_repo = SimpleNamespace(
        get_by_doctor_and_day=AsyncMock(
            return_value=[
                SimpleNamespace(
                    start_time=time(8, 0),
                    end_time=time(12, 0),
                    break_start=time(10, 0),
                    break_end=time(10, 30),
                    max_patients=12,
                )
            ]
        )
    )
    day_off_repo = SimpleNamespace(is_day_off=AsyncMock(return_value=False))
    service_repo = SimpleNamespace(
        list_by_doctor=AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=uuid4(), service_name="General", duration_minutes=30, fee=200000, is_active=True
                ),
                SimpleNamespace(
                    id=uuid4(), service_name="Legacy", duration_minutes=20, fee=100000, is_active=False
                ),
            ]
        )
    )

    use_case = GetEnhancedScheduleUseCase(availability_repo, day_off_repo, service_repo)
    result = await use_case.execute(doctor_id=doctor_id, target_date=target_date)

    assert result["is_day_off"] is False
    assert result["working_hours"] == [
        {
            "start_time": "08:00:00",
            "end_time": "12:00:00",
            "max_patients": 12,
            "break_start": "10:00:00",
            "break_end": "10:30:00",
        }
    ]
    assert len(result["services"]) == 1
    assert result["services"][0]["service_name"] == "General"


@pytest.mark.asyncio
async def test_get_enhanced_schedule_returns_empty_windows_when_no_availability():
    doctor_id = uuid4()
    target_date = date(2026, 3, 31)

    availability_repo = SimpleNamespace(get_by_doctor_and_day=AsyncMock(return_value=[]))
    day_off_repo = SimpleNamespace(is_day_off=AsyncMock(return_value=True))
    service_repo = SimpleNamespace(list_by_doctor=AsyncMock())

    use_case = GetEnhancedScheduleUseCase(availability_repo, day_off_repo, service_repo)
    result = await use_case.execute(doctor_id=doctor_id, target_date=target_date)

    assert result["is_day_off"] is True
    assert result["working_hours"] == []
    assert result["services"] == []
    service_repo.list_by_doctor.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_and_get_availability_calls_repositories():
    doctor_id = uuid4()
    session = SimpleNamespace(commit=AsyncMock())
    availability_repo = SimpleNamespace(
        upsert=AsyncMock(return_value={"saved": True}),
        get_by_doctor=AsyncMock(return_value=[{"day_of_week": 1}]),
        session=session,
    )

    set_use_case = SetAvailabilityUseCase(availability_repo)
    saved = await set_use_case.execute(
        doctor_id=doctor_id,
        day_of_week=1,
        start_time=time(8, 0),
        end_time=time(12, 0),
        break_start=time(10, 0),
        break_end=time(10, 30),
        max_patients=10,
    )
    assert saved == {"saved": True}
    availability_repo.upsert.assert_awaited_once()
    session.commit.assert_awaited_once()

    get_use_case = GetAvailabilityUseCase(availability_repo)
    loaded = await get_use_case.execute(doctor_id)
    assert loaded == [{"day_of_week": 1}]
    availability_repo.get_by_doctor.assert_awaited_once_with(doctor_id)


@pytest.mark.asyncio
async def test_manage_day_off_add_and_remove():
    doctor_id = uuid4()
    off_date = date(2026, 4, 2)
    day_off_repo = SimpleNamespace(create=AsyncMock(return_value={"ok": True}), delete=AsyncMock(return_value=1))

    add_use_case = AddDayOffUseCase(day_off_repo)
    remove_use_case = RemoveDayOffUseCase(day_off_repo)

    assert await add_use_case.execute(doctor_id, off_date, "vacation") == {"ok": True}
    assert await remove_use_case.execute(doctor_id, off_date) == 1
    day_off_repo.create.assert_awaited_once_with(doctor_id, off_date, "vacation")
    day_off_repo.delete.assert_awaited_once_with(doctor_id, off_date)


@pytest.mark.asyncio
async def test_manage_service_offerings_add_list_update_deactivate():
    doctor_id = uuid4()
    service_id = uuid4()
    service_repo = SimpleNamespace(
        create=AsyncMock(return_value={"id": service_id}),
        list_by_doctor=AsyncMock(return_value=[{"id": service_id}]),
        update=AsyncMock(return_value={"updated": True}),
        deactivate=AsyncMock(return_value=True),
    )

    assert await AddServiceOfferingUseCase(service_repo).execute(doctor_id, "General", 30, 100000, "desc") == {
        "id": service_id
    }
    assert await ListServiceOfferingsUseCase(service_repo).execute(doctor_id) == [{"id": service_id}]
    assert await UpdateServiceOfferingUseCase(service_repo).execute(service_id, fee=120000) == {"updated": True}
    assert await DeactivateServiceOfferingUseCase(service_repo).execute(service_id) is True


@pytest.mark.asyncio
async def test_submit_rating_requires_completed_appointment_and_updates_average():
    doctor_id = uuid4()
    patient_id = uuid4()
    appointment_id = uuid4()

    appointment_repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                patient_id=patient_id,
                doctor_id=doctor_id,
                status="COMPLETED",
            )
        )
    )
    rating_repo = SimpleNamespace(
        get_by_patient_and_doctor=AsyncMock(return_value=None),
        create=AsyncMock(return_value={"rating": 5}),
        get_average_rating=AsyncMock(return_value=4.5),
    )
    doctor_repo = SimpleNamespace(update_average_rating=AsyncMock())

    use_case = SubmitRatingUseCase(rating_repo=rating_repo, doctor_repo=doctor_repo, appointment_repo=appointment_repo)
    result = await use_case.execute(doctor_id, patient_id, rating=5, comment="great", appointment_id=appointment_id)

    assert result == {"rating": 5}
    rating_repo.create.assert_awaited_once_with(doctor_id, patient_id, 5, "great")
    doctor_repo.update_average_rating.assert_awaited_once_with(doctor_id, 4.5)


@pytest.mark.asyncio
async def test_submit_rating_blocks_when_appointment_not_completed():
    doctor_id = uuid4()
    patient_id = uuid4()
    appointment_id = uuid4()

    appointment_repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                patient_id=patient_id,
                doctor_id=doctor_id,
                status="CONFIRMED",
            )
        )
    )
    rating_repo = SimpleNamespace(get_by_patient_and_doctor=AsyncMock())
    doctor_repo = SimpleNamespace(update_average_rating=AsyncMock())

    use_case = SubmitRatingUseCase(rating_repo=rating_repo, doctor_repo=doctor_repo, appointment_repo=appointment_repo)

    with pytest.raises(ValueError, match="Invalid appointment for rating"):
        await use_case.execute(doctor_id, patient_id, rating=4, appointment_id=appointment_id)


@pytest.mark.asyncio
async def test_list_ratings_pagination_uses_limit_and_offset():
    doctor_id = uuid4()
    rating_repo = SimpleNamespace(list_by_doctor=AsyncMock(return_value=[{"id": 1}]))

    use_case = ListRatingsUseCase(rating_repo=rating_repo)
    result = await use_case.execute(doctor_id=doctor_id, page=2, limit=15)

    assert result == [{"id": 1}]
    rating_repo.list_by_doctor.assert_awaited_once_with(doctor_id, 15, 15)
