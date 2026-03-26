from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from Application.exceptions import (
    AppointmentError,
    AppointmentNotFoundError,
    DoctorNotAvailableError,
    InvalidAppointmentStatusError,
    SlotNotAvailableError,
)
from Application.use_cases.get_appointment_stats import GetAppointmentStatsUseCase
from Application.use_cases.list_doctor_appointments import ListDoctorAppointmentsUseCase
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus


def test_application_exception_hierarchy():
    assert issubclass(SlotNotAvailableError, AppointmentError)
    assert issubclass(DoctorNotAvailableError, AppointmentError)
    assert issubclass(AppointmentNotFoundError, AppointmentError)
    assert issubclass(InvalidAppointmentStatusError, AppointmentError)


@pytest.mark.asyncio
async def test_get_appointment_stats_month_range(monkeypatch):
    doctor_id = uuid4()
    repo = SimpleNamespace(list_by_doctor=AsyncMock(return_value=[]))
    use_case = GetAppointmentStatsUseCase(appointment_repo=repo)

    fake_today = date(2026, 3, 30)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return fake_today

    monkeypatch.setattr("Application.use_cases.get_appointment_stats.date", FakeDate)

    await use_case.execute(doctor_id=doctor_id, range_type="month")

    month_start = fake_today.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    repo.list_by_doctor.assert_awaited_once_with(doctor_id, month_start, month_end)


@pytest.mark.asyncio
async def test_get_appointment_stats_today_range_default(monkeypatch):
    doctor_id = uuid4()
    repo = SimpleNamespace(list_by_doctor=AsyncMock(return_value=[]))
    use_case = GetAppointmentStatsUseCase(appointment_repo=repo)

    fake_today = date(2026, 3, 30)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return fake_today

    monkeypatch.setattr("Application.use_cases.get_appointment_stats.date", FakeDate)

    await use_case.execute(doctor_id=doctor_id, range_type="today")

    repo.list_by_doctor.assert_awaited_once_with(doctor_id, fake_today, fake_today)


@pytest.mark.asyncio
async def test_list_doctor_appointments_returns_response_models():
    doctor_id = uuid4()
    appt = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        doctor_id=doctor_id,
        specialty_id=uuid4(),
        appointment_date=date(2026, 3, 30),
        start_time=time(10, 0),
        end_time=time(10, 30),
        appointment_type="general",
        chief_complaint=None,
        note_for_doctor=None,
        status=AppointmentStatus.CONFIRMED,
        payment_status=PaymentStatus.PAID,
        queue_number=1,
        started_at=None,
    )
    repo = SimpleNamespace(list_by_doctor=AsyncMock(return_value=[appt]))

    use_case = ListDoctorAppointmentsUseCase(appointment_repo=repo)
    result = await use_case.execute(doctor_id=doctor_id, date_from=date(2026, 3, 1), date_to=date(2026, 3, 31))

    assert len(result) == 1
    assert result[0].doctor_id == doctor_id
    repo.list_by_doctor.assert_awaited_once()
