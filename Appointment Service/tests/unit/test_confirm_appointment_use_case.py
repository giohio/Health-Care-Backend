import asyncio
from datetime import date, time
from uuid import uuid4

import pytest
from Application.use_cases.confirm_appointment import ConfirmAppointmentUseCase
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

    async def get_next_queue_number(self, doctor_id, appointment_date):
        await asyncio.sleep(0)
        return 1


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


class FakeAppointment:
    def __init__(self, doctor_id=None, can_confirm=True):
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
        self.status = AppointmentStatus.PENDING
        self.payment_status = PaymentStatus.PAID
        self.queue_number = None
        self.confirmed_at = None
        self._can_confirm = can_confirm

    def can_be_confirmed_by(self, doctor_id):
        return self._can_confirm and doctor_id == self.doctor_id

    def can_transition_to(self, target):
        return bool(self._can_confirm and target == AppointmentStatus.CONFIRMED)


@pytest.mark.asyncio
async def test_confirm_appointment_by_assigned_doctor():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, can_confirm=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = ConfirmAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    result = await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id)

    assert result.status == AppointmentStatus.CONFIRMED
    assert appointment.status == AppointmentStatus.CONFIRMED
    assert appointment.confirmed_at is not None
    assert appointment.queue_number == 1
    assert session.commits == 1
    assert len(repo.saved) == 1
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["event_type"] == "appointment.confirmed"


@pytest.mark.asyncio
async def test_confirm_appointment_not_found_raises():
    session = FakeSession()
    repo = FakeRepo(None)
    publisher = FakePublisher()
    use_case = ConfirmAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(AppointmentNotFoundException):
        await use_case.execute(appointment_id=uuid4(), doctor_id=uuid4())


@pytest.mark.asyncio
async def test_confirm_appointment_wrong_doctor_raises():
    correct_doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=correct_doctor_id, can_confirm=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = ConfirmAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(UnauthorizedActionError):
        await use_case.execute(appointment_id=appointment.id, doctor_id=uuid4())


@pytest.mark.asyncio
async def test_confirm_appointment_invalid_transition_raises():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, can_confirm=True)
    appointment.status = AppointmentStatus.COMPLETED

    def mock_can_transition(target):
        return False

    appointment.can_transition_to = mock_can_transition

    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = ConfirmAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(InvalidStatusTransitionError):
        await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id)


@pytest.mark.asyncio
async def test_confirm_appointment_assigns_queue_number():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, can_confirm=True)
    session = FakeSession()

    class CustomRepo(FakeRepo):
        queue_call_count = 0

        async def get_next_queue_number(self, doctor_id, appointment_date):
            await asyncio.sleep(0)
            self.queue_call_count += 1
            return 5

    repo = CustomRepo(appointment)
    publisher = FakePublisher()

    use_case = ConfirmAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id)

    assert appointment.queue_number == 5
    assert repo.queue_call_count == 1
