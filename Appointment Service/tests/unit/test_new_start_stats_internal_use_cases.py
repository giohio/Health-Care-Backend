from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from Application.use_cases.get_appointment_stats import GetAppointmentStatsUseCase
from Application.use_cases.start_appointment import StartAppointmentUseCase
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
    UnauthorizedActionError,
)
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from presentation.routes.internal import get_upcoming_appointments, mark_reminder_sent


@pytest.mark.asyncio
async def test_start_appointment_transitions_confirmed_to_in_progress_and_publishes_event(monkeypatch):
    appointment_id = uuid4()
    doctor_id = uuid4()
    patient_id = uuid4()
    fixed_now = datetime(2026, 3, 30, 10, 15, tzinfo=timezone.utc)

    appt = SimpleNamespace(
        id=appointment_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        specialty_id=uuid4(),
        appointment_date=date(2026, 3, 30),
        start_time=time(10, 0),
        end_time=time(10, 30),
        appointment_type="general",
        chief_complaint="headache",
        note_for_doctor=None,
        status=AppointmentStatus.CONFIRMED,
        payment_status=PaymentStatus.UNPAID,
        queue_number=1,
        started_at=None,
        can_transition_to=lambda target: target == AppointmentStatus.IN_PROGRESS,
    )

    monkeypatch.setattr("Application.use_cases.start_appointment.utcnow", lambda: fixed_now)

    repo = SimpleNamespace(get_by_id_with_lock=AsyncMock(return_value=appt), save=AsyncMock())
    publisher = SimpleNamespace(publish=AsyncMock())
    session = SimpleNamespace(commit=AsyncMock())

    use_case = StartAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    result = await use_case.execute(appointment_id=appointment_id, doctor_id=doctor_id)

    assert result.id == appointment_id
    assert appt.status == AppointmentStatus.IN_PROGRESS
    assert appt.started_at == fixed_now
    repo.save.assert_awaited_once_with(appt)
    publisher.publish.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_appointment_blocks_unauthorized_doctor():
    appointment_id = uuid4()
    assigned_doctor_id = uuid4()
    caller_doctor_id = uuid4()

    appt = SimpleNamespace(
        id=appointment_id,
        doctor_id=assigned_doctor_id,
        can_transition_to=lambda _target: True,
    )
    repo = SimpleNamespace(get_by_id_with_lock=AsyncMock(return_value=appt), save=AsyncMock())
    publisher = SimpleNamespace(publish=AsyncMock())
    session = SimpleNamespace(commit=AsyncMock())

    use_case = StartAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(UnauthorizedActionError):
        await use_case.execute(appointment_id=appointment_id, doctor_id=caller_doctor_id)


@pytest.mark.asyncio
async def test_start_appointment_not_found_and_invalid_transition():
    session = SimpleNamespace(commit=AsyncMock())
    publisher = SimpleNamespace(publish=AsyncMock())

    not_found_repo = SimpleNamespace(get_by_id_with_lock=AsyncMock(return_value=None), save=AsyncMock())
    not_found_use_case = StartAppointmentUseCase(
        session=session,
        appointment_repo=not_found_repo,
        event_publisher=publisher,
    )
    with pytest.raises(AppointmentNotFoundException):
        await not_found_use_case.execute(uuid4(), uuid4())

    appt = SimpleNamespace(
        id=uuid4(),
        doctor_id=uuid4(),
        can_transition_to=lambda _target: False,
    )
    invalid_repo = SimpleNamespace(get_by_id_with_lock=AsyncMock(return_value=appt), save=AsyncMock())
    invalid_use_case = StartAppointmentUseCase(session=session, appointment_repo=invalid_repo, event_publisher=publisher)
    with pytest.raises(InvalidStatusTransitionError):
        await invalid_use_case.execute(appt.id, appt.doctor_id)


@pytest.mark.asyncio
async def test_get_appointment_stats_groups_counts_by_status(monkeypatch):
    class StatusObj:
        def __init__(self, value):
            self.value = value

    doctor_id = uuid4()
    items = [
        SimpleNamespace(status=StatusObj("PENDING")),
        SimpleNamespace(status=StatusObj("CONFIRMED")),
        SimpleNamespace(status=StatusObj("COMPLETED")),
        SimpleNamespace(status=StatusObj("CANCELLED")),
        SimpleNamespace(status=StatusObj("PENDING_PAYMENT")),
    ]

    repo = SimpleNamespace(list_by_doctor=AsyncMock(return_value=items))
    use_case = GetAppointmentStatsUseCase(appointment_repo=repo)

    fake_today = date(2026, 3, 30)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return fake_today

    monkeypatch.setattr("Application.use_cases.get_appointment_stats.date", FakeDate)

    result = await use_case.execute(doctor_id=doctor_id, range_type="week")

    assert result == {
        "total_appointments": 5,
        "booked_appointments": 3,
        "pending_appointments": 1,
        "confirmed_appointments": 1,
        "completed_appointments": 1,
        "cancelled_appointments": 1,
    }
    repo.list_by_doctor.assert_awaited_once_with(doctor_id, fake_today, fake_today + timedelta(days=7))


@pytest.mark.asyncio
async def test_internal_routes_upcoming_and_mark_reminder_sent():
    appt = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        appointment_date=date(2026, 3, 31),
        start_time=time(9, 0),
        reminder_24h_sent=False,
        reminder_1h_sent=True,
    )
    repo = SimpleNamespace(
        get_upcoming_for_reminders=AsyncMock(return_value=[appt]),
        mark_reminder_sent=AsyncMock(),
    )

    upcoming = await get_upcoming_appointments(
        start_time="2026-03-30T08:00:00",
        end_time="2026-03-31T10:00:00",
        repo=repo,
    )
    assert len(upcoming) == 1
    assert upcoming[0]["id"] == str(appt.id)

    marked = await mark_reminder_sent(appointment_id=appt.id, reminder_type="24h", repo=repo)
    assert marked == {"success": True}
    repo.mark_reminder_sent.assert_awaited_once_with(appt.id, "24h")
