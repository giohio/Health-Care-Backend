import asyncio
from datetime import date, time
from uuid import uuid4

import pytest
from Application.use_cases.cancel_appointment import CancelAppointmentUseCase
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
    UnauthorizedActionError,
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
    def __init__(self, patient_id=None, doctor_id=None, payment_status=PaymentStatus.PAID, can_cancel=True):
        self.id = uuid4()
        self.patient_id = patient_id or uuid4()
        self.doctor_id = doctor_id or uuid4()
        self.specialty_id = uuid4()
        self.appointment_date = date(2026, 3, 30)
        self.start_time = time(10, 0)
        self.end_time = time(10, 30)
        self.appointment_type = "general"
        self.chief_complaint = None
        self.note_for_doctor = None
        self.status = AppointmentStatus.PENDING
        self.payment_status = payment_status
        self.queue_number = None
        self.cancelled_by = None
        self.cancelled_by_user_id = None
        self.cancelled_at = None
        self.cancel_reason = None
        self._can_cancel = can_cancel

    def can_be_cancelled_by(self, actor_id, actor_role):
        return self._can_cancel and actor_id == self.patient_id

    def can_transition_to(self, target):
        return bool(self._can_cancel and target == AppointmentStatus.CANCELLED)


@pytest.mark.asyncio
async def test_cancel_appointment_by_patient_refunds_if_paid():
    patient_id = uuid4()
    appointment = FakeAppointment(
        patient_id=patient_id,
        payment_status=PaymentStatus.PAID,
        can_cancel=True,
    )
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    cache = FakeCache()

    use_case = CancelAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher, cache=cache)
    result = await use_case.execute(
        appointment_id=appointment.id,
        actor_id=patient_id,
        actor_role="patient",
        reason="Having fever",
    )

    assert result.status == AppointmentStatus.CANCELLED
    assert appointment.status == AppointmentStatus.CANCELLED
    assert appointment.payment_status == PaymentStatus.REFUNDED
    assert appointment.cancelled_by == "patient"
    assert appointment.cancelled_by_user_id == patient_id
    assert appointment.cancel_reason == "Having fever"
    assert session.commits == 1
    assert len(repo.saved) == 1
    assert len(publisher.calls) == 2
    assert publisher.calls[0]["event_type"] == "appointment.cancelled"
    assert publisher.calls[1]["event_type"] == "payment.refund_requested"
    assert cache.patterns == [f"slots:{appointment.doctor_id}:{appointment.appointment_date}:*"]
    assert cache.keys == [f"queue:{appointment.doctor_id}:{appointment.appointment_date}"]


@pytest.mark.asyncio
async def test_cancel_appointment_by_admin_works():
    admin_id = uuid4()
    appointment = FakeAppointment(patient_id=uuid4(), payment_status=PaymentStatus.PROCESSING, can_cancel=True)

    def mock_can_cancel_admin(actor_id, actor_role):
        return actor_role == "admin"

    appointment.can_be_cancelled_by = mock_can_cancel_admin

    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = CancelAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    await use_case.execute(
        appointment_id=appointment.id,
        actor_id=admin_id,
        actor_role="admin",
        reason="Admin cancel",
    )

    assert appointment.status == AppointmentStatus.CANCELLED
    assert appointment.cancelled_by == "admin"
    assert appointment.payment_status == PaymentStatus.PROCESSING


@pytest.mark.asyncio
async def test_cancel_appointment_without_reason_works():
    patient_id = uuid4()
    appointment = FakeAppointment(patient_id=patient_id, payment_status=PaymentStatus.PAID, can_cancel=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = CancelAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    await use_case.execute(appointment_id=appointment.id, actor_id=patient_id, actor_role="patient", reason=None)

    assert appointment.cancel_reason is None
    assert appointment.status == AppointmentStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_appointment_not_found_raises():
    session = FakeSession()
    repo = FakeRepo(None)
    publisher = FakePublisher()
    use_case = CancelAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(AppointmentNotFoundException):
        await use_case.execute(appointment_id=uuid4(), actor_id=uuid4(), actor_role="patient", reason="x")


@pytest.mark.asyncio
async def test_cancel_appointment_unauthorized_actor_raises():
    appointment = FakeAppointment(patient_id=uuid4(), can_cancel=True)

    def mock_can_cancel(actor_id, actor_role):
        return False

    appointment.can_be_cancelled_by = mock_can_cancel

    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = CancelAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(UnauthorizedActionError):
        await use_case.execute(appointment_id=appointment.id, actor_id=uuid4(), actor_role="other", reason="x")


@pytest.mark.asyncio
async def test_cancel_appointment_invalid_transition_raises():
    patient_id = uuid4()
    appointment = FakeAppointment(patient_id=patient_id, payment_status=PaymentStatus.PAID, can_cancel=True)
    appointment.status = AppointmentStatus.COMPLETED

    def mock_can_transition(target):
        return False

    appointment.can_transition_to = mock_can_transition

    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = CancelAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(InvalidStatusTransitionError):
        await use_case.execute(appointment_id=appointment.id, actor_id=patient_id, actor_role="patient", reason="x")
