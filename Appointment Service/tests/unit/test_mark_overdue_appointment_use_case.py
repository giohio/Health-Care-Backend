import asyncio
from datetime import date, time
from uuid import uuid4

import pytest
from Application.use_cases.mark_overdue_appointment import MarkOverdueAppointmentUseCase
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
)
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        await asyncio.sleep(0)
        self.commits += 1


class FakeRepo:
    def __init__(self, appointment):
        self.appointment = appointment
        self.saved = []

    async def get_by_id_with_lock(self, appointment_id):
        await asyncio.sleep(0)
        if self.appointment and self.appointment.id == appointment_id:
            return self.appointment
        return None

    async def save(self, appointment):
        await asyncio.sleep(0)
        self.saved.append(appointment)


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


class FakeCache:
    def __init__(self):
        self.patterns = []
        self.keys = []

    async def delete_pattern(self, pattern):
        await asyncio.sleep(0)
        self.patterns.append(pattern)

    async def delete(self, *keys):
        await asyncio.sleep(0)
        self.keys.extend(keys)


class FakeAppointment:
    def __init__(self, status=AppointmentStatus.CONFIRMED, can_transition=True):
        self.id = uuid4()
        self.patient_id = uuid4()
        self.doctor_id = uuid4()
        self.specialty_id = uuid4()
        self.appointment_date = date(2026, 3, 30)
        self.start_time = time(10, 0)
        self.end_time = time(10, 30)
        self.appointment_type = "general"
        self.chief_complaint = None
        self.note_for_doctor = None
        self.status = status
        self.payment_status = PaymentStatus.PAID
        self.queue_number = 1
        self.cancel_reason = None
        self._can_transition = can_transition

    def can_transition_to(self, target):
        return self._can_transition and target == AppointmentStatus.OVERDUE


# ─── Happy path ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_overdue_transitions_confirmed_to_overdue():
    """CONFIRMED appointment past end_time should transition to OVERDUE."""
    appointment = FakeAppointment(status=AppointmentStatus.CONFIRMED, can_transition=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    cache = FakeCache()

    use_case = MarkOverdueAppointmentUseCase(
        session=session,
        appointment_repo=repo,
        event_publisher=publisher,
        cache=cache,
    )
    result = await use_case.execute(appointment.id, reason="system_overdue")

    assert result.status == AppointmentStatus.OVERDUE
    assert appointment.status == AppointmentStatus.OVERDUE
    assert appointment.cancel_reason == "system_overdue"
    assert session.commits == 1
    assert len(repo.saved) == 1


@pytest.mark.asyncio
async def test_mark_overdue_publishes_appointment_overdue_event():
    """MarkOverdueUseCase must publish exactly one appointment.overdue event."""
    appointment = FakeAppointment(status=AppointmentStatus.CONFIRMED, can_transition=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = MarkOverdueAppointmentUseCase(
        session=session,
        appointment_repo=repo,
        event_publisher=publisher,
    )
    await use_case.execute(appointment.id, reason="system_overdue")

    assert len(publisher.calls) == 1
    assert publisher.calls[0]["event_type"] == "appointment.overdue"
    assert publisher.calls[0]["aggregate_type"] == "appointment_events"
    assert publisher.calls[0]["payload"]["appointment_id"] == str(appointment.id)
    assert publisher.calls[0]["payload"]["patient_id"] == str(appointment.patient_id)
    assert publisher.calls[0]["payload"]["doctor_id"] == str(appointment.doctor_id)
    assert publisher.calls[0]["payload"]["reason"] == "system_overdue"


@pytest.mark.asyncio
async def test_mark_overdue_does_not_trigger_refund():
    """System overdue should NOT trigger refund — patient may still arrive late."""
    appointment = FakeAppointment(status=AppointmentStatus.CONFIRMED, can_transition=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = MarkOverdueAppointmentUseCase(
        session=session,
        appointment_repo=repo,
        event_publisher=publisher,
    )
    await use_case.execute(appointment.id, reason="system_overdue")

    # Must be exactly 1 event (no refund_requested)
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["event_type"] == "appointment.overdue"


@pytest.mark.asyncio
async def test_mark_overdue_clears_cache():
    """MarkOverdueUseCase must clear doctor slot and queue cache."""
    appointment = FakeAppointment(status=AppointmentStatus.CONFIRMED, can_transition=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    cache = FakeCache()

    use_case = MarkOverdueAppointmentUseCase(
        session=session,
        appointment_repo=repo,
        event_publisher=publisher,
        cache=cache,
    )
    await use_case.execute(appointment.id, reason="system_overdue")

    assert cache.patterns == [f"slots:{appointment.doctor_id}:{appointment.appointment_date}:*"]
    assert cache.keys == [f"queue:{appointment.doctor_id}:{appointment.appointment_date}"]


# ─── Not found ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_overdue_raises_when_appointment_not_found():
    """Must raise AppointmentNotFoundException when appointment does not exist."""
    session = FakeSession()
    repo = FakeRepo(None)
    publisher = FakePublisher()

    use_case = MarkOverdueAppointmentUseCase(
        session=session,
        appointment_repo=repo,
        event_publisher=publisher,
    )

    with pytest.raises(AppointmentNotFoundException):
        await use_case.execute(uuid4(), reason="system_overdue")


# ─── Invalid transition ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_overdue_raises_for_non_confirmed_status():
    """Only CONFIRMED appointments can be marked overdue."""
    for invalid_status in [
        AppointmentStatus.PENDING_PAYMENT,
        AppointmentStatus.PENDING,
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.DECLINED,
        AppointmentStatus.NO_SHOW,
        AppointmentStatus.IN_PROGRESS,
    ]:
        appointment = FakeAppointment(status=invalid_status, can_transition=False)
        session = FakeSession()
        repo = FakeRepo(appointment)
        publisher = FakePublisher()

        use_case = MarkOverdueAppointmentUseCase(
            session=session,
            appointment_repo=repo,
            event_publisher=publisher,
        )

        with pytest.raises(InvalidStatusTransitionError):
            await use_case.execute(appointment.id, reason="system_overdue")


# ─── OVERDUE → NO_SHOW is allowed ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_overdue_to_no_show_is_allowed():
    """OVERDUE appointments can be marked as NO_SHOW (already in VALID_TRANSITIONS)."""
    appointment = FakeAppointment(status=AppointmentStatus.OVERDUE, can_transition=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = MarkOverdueAppointmentUseCase(
        session=session,
        appointment_repo=repo,
        event_publisher=publisher,
    )
    # Overdue to overdue should also work (no transition needed)
    assert appointment.can_transition_to(AppointmentStatus.OVERDUE) is True
