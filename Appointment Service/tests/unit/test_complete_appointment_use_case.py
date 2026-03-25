from datetime import date, time
from uuid import uuid4
import asyncio

import pytest

from Application.use_cases.complete_appointment import CompleteAppointmentUseCase
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
    def __init__(self, doctor_id=None, can_complete=True):
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
        self.payment_status = PaymentStatus.PAID
        self.queue_number = 1
        self.completed_at = None
        self._can_complete = can_complete

    def can_transition_to(self, target):
        return bool(self._can_complete and target == AppointmentStatus.COMPLETED)


@pytest.mark.asyncio
async def test_complete_appointment_by_assigned_doctor():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, can_complete=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()

    use_case = CompleteAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)
    result = await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id)

    assert result.status == AppointmentStatus.COMPLETED
    assert appointment.status == AppointmentStatus.COMPLETED
    assert appointment.completed_at is not None
    assert session.commits == 1
    assert len(repo.saved) == 1
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["event_type"] == "appointment.completed"
    assert publisher.calls[0]["payload"]["appointment_id"] == str(appointment.id)
    assert publisher.calls[0]["payload"]["doctor_id"] == str(doctor_id)


@pytest.mark.asyncio
async def test_complete_appointment_not_found_raises():
    session = FakeSession()
    repo = FakeRepo(None)
    publisher = FakePublisher()
    use_case = CompleteAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(AppointmentNotFoundException):
        await use_case.execute(appointment_id=uuid4(), doctor_id=uuid4())


@pytest.mark.asyncio
async def test_complete_appointment_wrong_doctor_raises():
    appointment = FakeAppointment(doctor_id=uuid4(), can_complete=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = CompleteAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(UnauthorizedActionError):
        await use_case.execute(appointment_id=appointment.id, doctor_id=uuid4())


@pytest.mark.asyncio
async def test_complete_appointment_invalid_transition_raises():
    doctor_id = uuid4()
    appointment = FakeAppointment(doctor_id=doctor_id, can_complete=False)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    use_case = CompleteAppointmentUseCase(session=session, appointment_repo=repo, event_publisher=publisher)

    with pytest.raises(InvalidStatusTransitionError):
        await use_case.execute(appointment_id=appointment.id, doctor_id=doctor_id)
