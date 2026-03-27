import asyncio
from datetime import date, time
from uuid import uuid4

import pytest
from Application.use_cases.reschedule_appointment import RescheduleAppointmentUseCase
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
    SlotNotAvailableError,
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

    async def is_slot_taken(self, doctor_id, appointment_date, start_time, end_time, exclude_id=None):
        await asyncio.sleep(0)
        return False


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


class FakeLockManager:
    def __init__(self, lock_available=True):
        self.lock_available = lock_available
        self.acquired_slots = []
        self.released_slots = []

    async def acquire_slot(self, doctor_id, appointment_date, start_time):
        await asyncio.sleep(0)
        if self.lock_available:
            token = f"lock_{doctor_id}_{appointment_date}_{start_time}"
            self.acquired_slots.append((doctor_id, appointment_date, start_time))
            return token
        return None

    async def release_slot(self, doctor_id, appointment_date, start_time, token=None):
        await asyncio.sleep(0)
        self.released_slots.append((doctor_id, appointment_date, start_time, token))


class FakeDoctorClient:
    def __init__(self, config=None):
        self.config = config or {"duration_minutes": 30, "buffer_minutes": 5}

    async def get_type_config(self, specialty_id, appointment_type):
        await asyncio.sleep(0)
        return self.config


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
    def __init__(self, patient_id=None, doctor_id=None, can_reschedule=True):
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
        self.status = AppointmentStatus.CONFIRMED
        self.payment_status = PaymentStatus.PAID
        self.queue_number = 1
        self._can_reschedule = can_reschedule

    def can_be_rescheduled_by(self, patient_id):
        return self._can_reschedule and patient_id == self.patient_id

    def can_transition_to(self, target):
        return self.status in (
            AppointmentStatus.PENDING_PAYMENT,
            AppointmentStatus.PENDING,
            AppointmentStatus.CONFIRMED,
        )


@pytest.mark.asyncio
async def test_reschedule_appointment_by_patient():
    patient_id = uuid4()
    doctor_id = uuid4()
    appointment = FakeAppointment(patient_id=patient_id, doctor_id=doctor_id, can_reschedule=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    lock_manager = FakeLockManager(lock_available=True)
    doctor_client = FakeDoctorClient()
    cache = FakeCache()

    use_case = RescheduleAppointmentUseCase(
        session=session,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
        cache=cache,
    )

    new_date = date(2026, 4, 5)
    new_time = time(14, 0)
    result = await use_case.execute(
        appointment_id=appointment.id,
        patient_id=patient_id,
        new_date=new_date,
        new_time=new_time,
    )

    assert result.appointment_date == new_date
    assert result.start_time == new_time
    assert len(repo.saved) == 1
    assert len(lock_manager.acquired_slots) == 1
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["event_type"] == "appointment.rescheduled"
    assert cache.patterns == [
        f"slots:{doctor_id}:{date(2026, 3, 30)}:*",
        f"slots:{doctor_id}:{new_date}:*",
    ]
    assert cache.keys == [
        f"queue:{doctor_id}:{date(2026, 3, 30)}",
        f"queue:{doctor_id}:{new_date}",
    ]


@pytest.mark.asyncio
async def test_reschedule_appointment_not_found_raises():
    session = FakeSession()
    repo = FakeRepo(None)
    publisher = FakePublisher()
    lock_manager = FakeLockManager()
    doctor_client = FakeDoctorClient()

    use_case = RescheduleAppointmentUseCase(
        session=session,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
    )

    with pytest.raises(AppointmentNotFoundException):
        await use_case.execute(
            appointment_id=uuid4(),
            patient_id=uuid4(),
            new_date=date(2026, 4, 5),
            new_time=time(14, 0),
        )


@pytest.mark.asyncio
async def test_reschedule_appointment_wrong_patient_raises():
    appointment = FakeAppointment(patient_id=uuid4(), can_reschedule=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    lock_manager = FakeLockManager()
    doctor_client = FakeDoctorClient()

    use_case = RescheduleAppointmentUseCase(
        session=session,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
    )

    with pytest.raises(UnauthorizedActionError):
        await use_case.execute(
            appointment_id=appointment.id,
            patient_id=uuid4(),
            new_date=date(2026, 4, 5),
            new_time=time(14, 0),
        )


@pytest.mark.asyncio
async def test_reschedule_appointment_lock_not_available_raises():
    patient_id = uuid4()
    appointment = FakeAppointment(patient_id=patient_id, can_reschedule=True)
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    lock_manager = FakeLockManager(lock_available=False)
    doctor_client = FakeDoctorClient()

    use_case = RescheduleAppointmentUseCase(
        session=session,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
    )

    with pytest.raises(SlotNotAvailableError):
        await use_case.execute(
            appointment_id=appointment.id,
            patient_id=patient_id,
            new_date=date(2026, 4, 5),
            new_time=time(14, 0),
        )


@pytest.mark.asyncio
async def test_reschedule_appointment_invalid_transition_raises():
    patient_id = uuid4()
    appointment = FakeAppointment(patient_id=patient_id, can_reschedule=True)
    appointment.status = AppointmentStatus.COMPLETED
    session = FakeSession()
    repo = FakeRepo(appointment)
    publisher = FakePublisher()
    lock_manager = FakeLockManager()
    doctor_client = FakeDoctorClient()

    use_case = RescheduleAppointmentUseCase(
        session=session,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
    )

    with pytest.raises(InvalidStatusTransitionError):
        await use_case.execute(
            appointment_id=appointment.id,
            patient_id=patient_id,
            new_date=date(2026, 4, 5),
            new_time=time(14, 0),
        )
