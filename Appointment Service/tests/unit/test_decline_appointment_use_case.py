from datetime import date, time
from uuid import uuid4
import asyncio

import pytest

from Application.use_cases.decline_appointment import DeclineAppointmentUseCase
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


class FakeAppointment:
    def __init__(self, doctor_id, payment_status=PaymentStatus.PAID, can_decline=True):
        self.id = uuid4()
        self.patient_id = uuid4()
        self.doctor_id = doctor_id
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
        self._can_decline = can_decline

    def can_transition_to(self, target):
        return bool(self._can_decline and target == AppointmentStatus.DECLINED)


@pytest.mark.asyncio
async def test_decline_appointment_paid_emits_decline_and_refund_request():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, payment_status=PaymentStatus.PAID, can_decline=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = DeclineAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    result = await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id, reason="Schedule conflict")

    assert result.status == AppointmentStatus.DECLINED
    assert appointment.status == AppointmentStatus.DECLINED
    assert appointment.payment_status == PaymentStatus.REFUNDED
    assert session.commits == 1
    assert len(repo.saved) == 1
    assert len(publisher.calls) == 2
    assert publisher.calls[0]["event_type"] == "appointment.declined"
    assert publisher.calls[1]["event_type"] == "payment.refund_requested"
    assert publisher.calls[1]["payload"]["appointment_marked_paid"] is True


@pytest.mark.asyncio
async def test_decline_appointment_unpaid_still_emits_refund_request_flag_false():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, payment_status=PaymentStatus.PROCESSING, can_decline=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = DeclineAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id, reason=None)

    assert appointment.payment_status == PaymentStatus.PROCESSING
    assert publisher.calls[1]["event_type"] == "payment.refund_requested"
    assert publisher.calls[1]["payload"]["appointment_marked_paid"] is False


@pytest.mark.asyncio
async def test_decline_appointment_not_found_raises():
    session = FakeSession()
    repo = FakeRepo(None)
    publisher = FakePublisher()
    use_case = DeclineAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(AppointmentNotFoundException):
        await use_case.execute(appointment_id=uuid4(), doctor_id=uuid4(), reason="x")


@pytest.mark.asyncio
async def test_decline_appointment_wrong_doctor_raises():
    appointment = FakeAppointment(doctor_id=uuid4(), payment_status=PaymentStatus.PAID, can_decline=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = DeclineAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(UnauthorizedActionError):
        await use_case.execute(appointment_id=appointment.id, doctor_id=uuid4(), reason="x")


@pytest.mark.asyncio
async def test_decline_appointment_invalid_transition_raises():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, payment_status=PaymentStatus.PAID, can_decline=False)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = DeclineAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(InvalidStatusTransitionError):
        await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id, reason="x")
