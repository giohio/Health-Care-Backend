import asyncio
from datetime import date, time
from uuid import uuid4

import pytest
from Application.use_cases.mark_no_show import MarkNoShowUseCase
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
    def __init__(self, doctor_id=None, payment_status=PaymentStatus.PAID, can_mark_no_show=True):
        self.id = uuid4()
        self.patient_id = uuid4()
        self.doctor_id = doctor_id or uuid4()
        self.specialty_id = uuid4()
        self.appointment_date = date(2026, 3, 30)
        self.start_time = time(10, 0)
        self.end_time = time(10, 30)
        self.appointment_type = "general"
        self.chief_complaint = None
        self.note_for_doctor = None
        self.status = AppointmentStatus.CONFIRMED
        self.payment_status = payment_status
        self.queue_number = 1
        self._can_mark_no_show = can_mark_no_show

    def can_transition_to(self, target):
        return bool(self._can_mark_no_show and target == AppointmentStatus.NO_SHOW)


@pytest.mark.asyncio
async def test_mark_no_show_by_doctor_refunds_if_paid():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, payment_status=PaymentStatus.PAID, can_mark_no_show=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = MarkNoShowUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    result = await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id)

    assert result.status == AppointmentStatus.NO_SHOW
    assert appointment.status == AppointmentStatus.NO_SHOW
    assert appointment.payment_status == PaymentStatus.REFUNDED
    assert session.commits == 1
    assert len(repo.saved) == 1
    assert len(publisher.calls) == 3
    assert publisher.calls[0]["event_type"] == "appointment.no_show"
    assert publisher.calls[1]["event_type"] == "cache.invalidate"
    assert publisher.calls[2]["event_type"] == "payment.refund_requested"


@pytest.mark.asyncio
async def test_mark_no_show_without_payment_refund_skips_refund_event():
    doctor_id = uuid4()
    appointment = FakeAppointment(
        doctor_id=doctor_id,
        payment_status=PaymentStatus.PROCESSING,
        can_mark_no_show=True,
    )
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = MarkNoShowUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id)

    assert appointment.status == AppointmentStatus.NO_SHOW
    assert appointment.payment_status == PaymentStatus.PROCESSING
    assert len(publisher.calls) == 2
    assert publisher.calls[0]["event_type"] == "appointment.no_show"
    assert publisher.calls[1]["event_type"] == "cache.invalidate"


@pytest.mark.asyncio
async def test_mark_no_show_invalidates_cache():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, can_mark_no_show=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = MarkNoShowUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id)

    cache_invalidation = publisher.calls[1]
    assert cache_invalidation["event_type"] == "cache.invalidate"
    assert cache_invalidation["payload"]["patterns"][0] == f"slots:{doctor_id}:{appointment.appointment_date}:*"
    assert cache_invalidation["payload"]["patterns"][1] == f"queue:{doctor_id}:{appointment.appointment_date}"


@pytest.mark.asyncio
async def test_mark_no_show_not_found_raises():
    session = FakeSession()
    repo = FakeRepo(None)
    publisher = FakePublisher()
    use_case = MarkNoShowUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(AppointmentNotFoundException):
        await use_case.execute(appointment_id=uuid4(), doctor_id=uuid4())


@pytest.mark.asyncio
async def test_mark_no_show_wrong_doctor_raises():
    appointment = FakeAppointment(doctor_id=uuid4(), can_mark_no_show=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = MarkNoShowUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(UnauthorizedActionError):
        await use_case.execute(appointment_id=appointment.id, doctor_id=uuid4())


@pytest.mark.asyncio
async def test_mark_no_show_invalid_transition_raises():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, payment_status=PaymentStatus.PAID, can_mark_no_show=False)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = MarkNoShowUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(InvalidStatusTransitionError):
        await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id)
