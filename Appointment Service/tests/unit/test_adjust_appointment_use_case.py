"""
Unit tests for AdjustAppointmentUseCase.

Key scenario tested: when a doctor extends their current appointment,
all subsequent CONFIRMED appointments in the queue must have their
start_time and end_time shifted by delay_minutes AND be saved to the repo.
"""

import asyncio
from datetime import date, time
from uuid import uuid4

import pytest
from Application.dtos import AdjustAppointmentRequest, AppointmentResponse
from Application.use_cases.adjust_appointment import AdjustAppointmentUseCase
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    UnauthorizedActionError,
)
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus


# ─── Fakes ────────────────────────────────────────────────────────────────────

class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        await asyncio.sleep(0)
        self.commits += 1


class FakeRepo:
    def __init__(self, appointment, queue=None):
        self.appointment = appointment
        self._queue = queue or []
        self.saved = []

    async def get_by_id_with_lock(self, appointment_id):
        await asyncio.sleep(0)
        if self.appointment and str(self.appointment.id) == str(appointment_id):
            return self.appointment
        return None

    async def save(self, appt):
        await asyncio.sleep(0)
        self.saved.append(appt)

    async def get_doctor_queue(self, doctor_id, appointment_date):
        await asyncio.sleep(0)
        return self._queue


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


class FakeAppointment:
    """Mimics the real Appointment entity well enough for the use case."""

    def __init__(
        self,
        doctor_id=None,
        start_time=time(10, 0),
        end_time=time(10, 30),
        status=AppointmentStatus.CONFIRMED,
    ):
        self.id = uuid4()
        self.patient_id = uuid4()
        self.doctor_id = doctor_id or uuid4()
        self.specialty_id = uuid4()
        self.appointment_date = date(2026, 4, 21)
        self.start_time = start_time
        self.end_time = end_time
        self.appointment_type = "general"
        self.chief_complaint = None
        self.note_for_doctor = None
        self.status = status
        self.payment_status = PaymentStatus.PAID
        self.queue_number = 1
        self.consultation_fee = 0
        self.confirmed_at = None
        self.started_at = None
        self.cancelled_at = None
        self.cancelled_by = None
        self.cancel_reason = None
        self.redirect_department = None
        self.triage_session_id = None
        self.ai_referred = False
        self.urgency_level = None
        self.referred_by_doctor_id = None

    def can_be_adjusted_by(self, doctor_id):
        return str(self.doctor_id) == str(doctor_id) and self.status in (
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.IN_PROGRESS,
        )


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adjust_updates_primary_appointment_end_time():
    """end_time of the adjusted appointment is updated correctly."""
    doctor_id = uuid4()
    appt = FakeAppointment(doctor_id=doctor_id, start_time=time(10, 0), end_time=time(10, 30))
    repo = FakeRepo(appt)
    use_case = AdjustAppointmentUseCase(FakeSession(), repo, FakePublisher())

    result = await use_case.execute(
        appointment_id=appt.id,
        doctor_id=doctor_id,
        request=AdjustAppointmentRequest(duration_minutes=45),
    )

    # Primary appointment saved exactly once
    assert repo.saved[0] is appt
    assert appt.end_time == time(10, 45)
    assert isinstance(result, AppointmentResponse)


@pytest.mark.asyncio
async def test_adjust_shifts_and_saves_subsequent_confirmed_appointments():
    """
    CRITICAL: subsequent CONFIRMED appointments must be shifted by delay_minutes
    AND saved to the repository (the bug we just fixed).
    """
    doctor_id = uuid4()
    # Primary appointment: 10:00 – 10:30 (30 min), being extended to 45 min (+15 delay)
    primary = FakeAppointment(doctor_id=doctor_id, start_time=time(10, 0), end_time=time(10, 30))

    # Two subsequent confirmed appointments in queue
    next1 = FakeAppointment(doctor_id=doctor_id, start_time=time(10, 30), end_time=time(11, 0))
    next1.queue_number = 2
    next2 = FakeAppointment(doctor_id=doctor_id, start_time=time(11, 0), end_time=time(11, 30))
    next2.queue_number = 3

    repo = FakeRepo(primary, queue=[primary, next1, next2])
    publisher = FakePublisher()
    use_case = AdjustAppointmentUseCase(FakeSession(), repo, publisher)

    await use_case.execute(
        appointment_id=primary.id,
        doctor_id=doctor_id,
        request=AdjustAppointmentRequest(duration_minutes=45),  # +15 min delay
    )

    # All three appointments should have been saved
    assert len(repo.saved) == 3, f"Expected 3 saves (primary + 2 subsequent), got {len(repo.saved)}"

    # next1 shifted +15
    assert next1.start_time == time(10, 45), f"next1.start_time should be 10:45, got {next1.start_time}"
    assert next1.end_time == time(11, 15), f"next1.end_time should be 11:15, got {next1.end_time}"

    # next2 shifted +15
    assert next2.start_time == time(11, 15), f"next2.start_time should be 11:15, got {next2.start_time}"
    assert next2.end_time == time(11, 45), f"next2.end_time should be 11:45, got {next2.end_time}"


@pytest.mark.asyncio
async def test_adjust_no_delay_does_not_touch_queue():
    """If duration doesn't change end_time, no queue shifting happens."""
    doctor_id = uuid4()
    # 10:00 – 10:30 (30 min), request same 30 min
    appt = FakeAppointment(doctor_id=doctor_id, start_time=time(10, 0), end_time=time(10, 30))
    next1 = FakeAppointment(doctor_id=doctor_id, start_time=time(10, 30), end_time=time(11, 0))

    repo = FakeRepo(appt, queue=[appt, next1])
    use_case = AdjustAppointmentUseCase(FakeSession(), repo, FakePublisher())

    await use_case.execute(
        appointment_id=appt.id,
        doctor_id=doctor_id,
        request=AdjustAppointmentRequest(duration_minutes=30),  # no change
    )

    # Only primary saved, next1 untouched
    assert len(repo.saved) == 1
    assert next1.start_time == time(10, 30)  # unchanged


@pytest.mark.asyncio
async def test_adjust_publishes_event_with_affected_patients():
    """Event payload must list affected patients with correct times."""
    doctor_id = uuid4()
    primary = FakeAppointment(doctor_id=doctor_id, start_time=time(9, 0), end_time=time(9, 20))
    subsequent = FakeAppointment(doctor_id=doctor_id, start_time=time(9, 20), end_time=time(9, 40))

    repo = FakeRepo(primary, queue=[primary, subsequent])
    publisher = FakePublisher()
    use_case = AdjustAppointmentUseCase(FakeSession(), repo, publisher)

    await use_case.execute(
        appointment_id=primary.id,
        doctor_id=doctor_id,
        request=AdjustAppointmentRequest(duration_minutes=30),  # +10 min
    )

    assert len(publisher.calls) == 1
    payload = publisher.calls[0]["payload"]
    assert payload["delay_minutes"] == 10
    assert len(payload["affected_patients"]) == 1
    affected = payload["affected_patients"][0]
    assert affected["original_start_time"] == "09:20"
    assert affected["new_estimated_start_time"] == "09:30"


@pytest.mark.asyncio
async def test_adjust_only_shifts_confirmed_not_other_statuses():
    """PENDING / COMPLETED / DECLINED appointments in queue are not shifted."""
    doctor_id = uuid4()
    primary = FakeAppointment(doctor_id=doctor_id, start_time=time(10, 0), end_time=time(10, 30))
    pending = FakeAppointment(doctor_id=doctor_id, start_time=time(10, 30), end_time=time(11, 0))
    pending.status = AppointmentStatus.PENDING
    completed = FakeAppointment(doctor_id=doctor_id, start_time=time(11, 0), end_time=time(11, 30))
    completed.status = AppointmentStatus.COMPLETED

    repo = FakeRepo(primary, queue=[primary, pending, completed])
    use_case = AdjustAppointmentUseCase(FakeSession(), repo, FakePublisher())

    await use_case.execute(
        appointment_id=primary.id,
        doctor_id=doctor_id,
        request=AdjustAppointmentRequest(duration_minutes=45),  # +15 min
    )

    # Only primary saved (pending + completed skipped)
    assert len(repo.saved) == 1
    assert pending.start_time == time(10, 30)   # unchanged
    assert completed.start_time == time(11, 0)  # unchanged


@pytest.mark.asyncio
async def test_adjust_raises_not_found_for_missing_appointment():
    repo = FakeRepo(appointment=None)
    use_case = AdjustAppointmentUseCase(FakeSession(), repo, FakePublisher())

    with pytest.raises(AppointmentNotFoundException):
        await use_case.execute(
            appointment_id=uuid4(),
            doctor_id=uuid4(),
            request=AdjustAppointmentRequest(duration_minutes=30),
        )


@pytest.mark.asyncio
async def test_adjust_raises_unauthorized_for_wrong_doctor():
    appt = FakeAppointment(doctor_id=uuid4())
    repo = FakeRepo(appt)
    use_case = AdjustAppointmentUseCase(FakeSession(), repo, FakePublisher())

    with pytest.raises(UnauthorizedActionError):
        await use_case.execute(
            appointment_id=appt.id,
            doctor_id=uuid4(),  # different doctor
            request=AdjustAppointmentRequest(duration_minutes=30),
        )


@pytest.mark.asyncio
async def test_adjust_updates_consultation_fee_when_provided():
    doctor_id = uuid4()
    appt = FakeAppointment(doctor_id=doctor_id)
    appt.consultation_fee = 100_000
    repo = FakeRepo(appt)
    use_case = AdjustAppointmentUseCase(FakeSession(), repo, FakePublisher())

    result = await use_case.execute(
        appointment_id=appt.id,
        doctor_id=doctor_id,
        request=AdjustAppointmentRequest(duration_minutes=30, consultation_fee=200_000),
    )

    assert appt.consultation_fee == 200_000
    assert result.consultation_fee == 200_000
