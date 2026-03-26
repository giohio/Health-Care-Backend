import asyncio
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from Application.use_cases.book_appointment import BookAppointmentSaga, BookAppointmentUseCase
from Application.dtos import CreateAppointmentRequest
from Domain.exceptions.domain_exceptions import SlotNotAvailableError
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from healthai_events.exceptions import NonRetryableError


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        await asyncio.sleep(0)
        self.commits += 1


class FakeCache:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        await asyncio.sleep(0)
        return self.data.get(key)

    async def set(self, key, value):
        await asyncio.sleep(0)
        self.data[key] = value


class FakeRepo:
    def __init__(self):
        self.appointments = {}
        self.saved = []

    async def save(self, appointment):
        await asyncio.sleep(0)
        self.appointments[appointment.id] = appointment
        self.saved.append(appointment)

    async def get_by_id(self, appointment_id):
        await asyncio.sleep(0)
        return self.appointments.get(appointment_id)

    async def is_slot_taken(self, doctor_id, appointment_date, start_time, end_time):
        await asyncio.sleep(0)
        return False


class FakeLockManager:
    def __init__(self, lock_available=True):
        self.lock_available = lock_available
        self.acquired = []
        self.released = []

    async def acquire_slot(self, doctor_id, appointment_date, start_time):
        await asyncio.sleep(0)
        if self.lock_available:
            token = f"lock_{doctor_id}_{appointment_date}_{start_time}"
            self.acquired.append((doctor_id, appointment_date, start_time))
            return token
        return None

    async def release_slot(self, doctor_id, appointment_date, start_time, token):
        await asyncio.sleep(0)
        self.released.append((doctor_id, appointment_date, start_time, token))


class FakeDoctorClient:
    def __init__(self, config=None):
        self.config = config or {"duration_minutes": 30, "amount": 200000}

    async def get_type_config(self, specialty_id, appointment_type):
        await asyncio.sleep(0)
        return self.config


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


class FakePricingPolicy:
    def default_amount_vnd(self):
        return 150000


class FakeSagaOrchestrator(BookAppointmentSaga):
    """Extends BookAppointmentSaga to add execute method for testing."""

    async def execute(self, ctx):
        """Simple sync execution for testing without full saga orchestration."""
        for step in self.STEPS:
            method_name = f"execute_{step}"
            if hasattr(self, method_name):
                method = getattr(self, method_name)
                await method(ctx)


@pytest.mark.asyncio
async def test_book_appointment_saga_validates_future_date():
    session = FakeSession()
    cache = FakeCache()
    lock_manager = FakeLockManager()
    repo = FakeRepo()
    doctor_client = FakeDoctorClient()
    publisher = FakePublisher()
    pricing_policy = FakePricingPolicy()

    saga = FakeSagaOrchestrator(
        session=session,
        cache=cache,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
        pricing_policy=pricing_policy,
    )

    ctx = {
        "patient_id": str(uuid4()),
        "doctor_id": str(uuid4()),
        "specialty_id": str(uuid4()),
        "appointment_date": date(2026, 1, 1),
        "start_time": time(10, 0),
        "appointment_type": "general",
    }

    with pytest.raises(NonRetryableError):
        await saga.execute_validate_input(ctx)


@pytest.mark.asyncio
async def test_book_appointment_saga_acquires_slot_lock():
    session = FakeSession()
    cache = FakeCache()
    lock_manager = FakeLockManager(lock_available=True)
    repo = FakeRepo()
    doctor_client = FakeDoctorClient()
    publisher = FakePublisher()
    pricing_policy = FakePricingPolicy()

    saga = FakeSagaOrchestrator(
        session=session,
        cache=cache,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
        pricing_policy=pricing_policy,
    )

    ctx = {
        "doctor_id": str(uuid4()),
        "appointment_date": str(date(2026, 3, 30)),
        "start_time": str(time(10, 0)),
    }

    await saga.execute_acquire_slot_lock(ctx)

    assert "lock_token" in ctx
    assert len(lock_manager.acquired) == 1


@pytest.mark.asyncio
async def test_book_appointment_saga_fails_without_available_slot():
    session = FakeSession()
    cache = FakeCache()
    lock_manager = FakeLockManager(lock_available=False)
    repo = FakeRepo()
    doctor_client = FakeDoctorClient()
    publisher = FakePublisher()
    pricing_policy = FakePricingPolicy()

    saga = FakeSagaOrchestrator(
        session=session,
        cache=cache,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
        pricing_policy=pricing_policy,
    )

    ctx = {
        "doctor_id": str(uuid4()),
        "appointment_date": str(date(2026, 3, 30)),
        "start_time": str(time(10, 0)),
    }

    with pytest.raises(SlotNotAvailableError):
        await saga.execute_acquire_slot_lock(ctx)


@pytest.mark.asyncio
async def test_book_appointment_saga_checks_slot_availability():
    session = FakeSession()
    cache = FakeCache()
    lock_manager = FakeLockManager()
    repo = FakeRepo()
    doctor_client = FakeDoctorClient(config={"duration_minutes": 30})
    publisher = FakePublisher()
    pricing_policy = FakePricingPolicy()

    saga = FakeSagaOrchestrator(
        session=session,
        cache=cache,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
        pricing_policy=pricing_policy,
    )

    ctx = {
        "doctor_id": str(uuid4()),
        "appointment_date": str(date(2026, 3, 30)),
        "start_time": str(time(10, 0)),
        "type_config": {"duration_minutes": 30},
    }

    await saga.execute_check_slot(ctx)

    assert "end_time" in ctx


@pytest.mark.asyncio
async def test_book_appointment_saga_creates_appointment():
    session = FakeSession()
    cache = FakeCache()
    lock_manager = FakeLockManager()
    repo = FakeRepo()
    doctor_client = FakeDoctorClient()
    publisher = FakePublisher()
    pricing_policy = FakePricingPolicy()

    saga = FakeSagaOrchestrator(
        session=session,
        cache=cache,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
        pricing_policy=pricing_policy,
    )

    patient_id = str(uuid4())
    doctor_id = str(uuid4())
    specialty_id = str(uuid4())

    ctx = {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "specialty_id": specialty_id,
        "appointment_date": str(date(2026, 3, 30)),
        "start_time": str(time(10, 0)),
        "end_time": str(time(10, 30)),
        "appointment_type": "general",
        "chief_complaint": "Headache",
        "note_for_doctor": "Severe headache",
    }

    appt = await saga.execute_create_appointment(ctx)

    assert appt is not None
    assert appt.status == AppointmentStatus.PENDING_PAYMENT
    assert appt.payment_status == PaymentStatus.PROCESSING
    assert appt.chief_complaint == "Headache"
    assert len(repo.saved) == 1


@pytest.mark.asyncio
async def test_book_appointment_saga_publishes_payment_event():
    session = FakeSession()
    cache = FakeCache()
    lock_manager = FakeLockManager()
    repo = FakeRepo()
    doctor_client = FakeDoctorClient(config={"duration_minutes": 30, "amount": 250000})
    publisher = FakePublisher()
    pricing_policy = FakePricingPolicy()

    saga = FakeSagaOrchestrator(
        session=session,
        cache=cache,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
        pricing_policy=pricing_policy,
    )

    patient_id = str(uuid4())
    doctor_id = str(uuid4())

    # First create an appointment
    ctx = {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "specialty_id": str(uuid4()),
        "appointment_date": str(date(2026, 3, 30)),
        "start_time": str(time(10, 0)),
        "end_time": str(time(10, 30)),
        "appointment_type": "general",
        "type_config": {"duration_minutes": 30, "amount": 250000},
    }

    appt = await saga.execute_create_appointment(ctx)
    ctx["appointment_id"] = str(appt.id)

    # Then write outbox
    await saga.execute_write_outbox(ctx)

    assert len(publisher.calls) == 2
    assert publisher.calls[0]["event_type"] == "appointment.payment_required"
    assert publisher.calls[0]["payload"]["amount"] == 250000
    assert publisher.calls[1]["event_type"] == "cache.invalidate"


@pytest.mark.asyncio
async def test_book_appointment_saga_uses_default_pricing():
    session = FakeSession()
    cache = FakeCache()
    lock_manager = FakeLockManager()
    repo = FakeRepo()
    doctor_client = FakeDoctorClient(config={"duration_minutes": 30})
    publisher = FakePublisher()
    pricing_policy = FakePricingPolicy()

    saga = FakeSagaOrchestrator(
        session=session,
        cache=cache,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
        pricing_policy=pricing_policy,
    )

    patient_id = str(uuid4())
    doctor_id = str(uuid4())

    ctx = {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "specialty_id": str(uuid4()),
        "appointment_date": str(date(2026, 3, 30)),
        "start_time": str(time(10, 0)),
        "end_time": str(time(10, 30)),
        "appointment_type": "general",
        "type_config": {"duration_minutes": 30},
    }

    appt = await saga.execute_create_appointment(ctx)
    ctx["appointment_id"] = str(appt.id)

    await saga.execute_write_outbox(ctx)

    assert len(publisher.calls) == 2
    assert publisher.calls[0]["payload"]["amount"] == 150000


@pytest.mark.asyncio
async def test_book_appointment_saga_releases_slot_lock():
    session = FakeSession()
    cache = FakeCache()
    lock_manager = FakeLockManager()
    repo = FakeRepo()
    doctor_client = FakeDoctorClient()
    publisher = FakePublisher()
    pricing_policy = FakePricingPolicy()

    saga = FakeSagaOrchestrator(
        session=session,
        cache=cache,
        lock_manager=lock_manager,
        appointment_repo=repo,
        doctor_client=doctor_client,
        event_publisher=publisher,
        pricing_policy=pricing_policy,
    )

    doctor_id = str(uuid4())
    ctx = {
        "doctor_id": doctor_id,
        "appointment_date": str(date(2026, 3, 30)),
        "start_time": str(time(10, 0)),
        "lock_token": f"lock_{doctor_id}_2026-03-30_10:00:00",
    }

    await saga.execute_release_slot_lock(ctx)

    assert len(lock_manager.released) == 1
    assert ctx["lock_token"] is None


@pytest.mark.asyncio
async def test_book_appointment_saga_validate_input_uses_default_config_when_missing():
    class NoConfigDoctorClient:
        async def get_type_config(self, specialty_id, appointment_type):
            await asyncio.sleep(0)
            return None

    saga = FakeSagaOrchestrator(
        session=FakeSession(),
        cache=FakeCache(),
        lock_manager=FakeLockManager(),
        appointment_repo=FakeRepo(),
        doctor_client=NoConfigDoctorClient(),
        event_publisher=FakePublisher(),
        pricing_policy=FakePricingPolicy(),
    )

    ctx = {
        "specialty_id": str(uuid4()),
        "appointment_type": "general",
        "appointment_date": str(date.today()),
    }

    await saga.execute_validate_input(ctx)

    assert ctx["type_config"] == {"duration_minutes": 30, "buffer_minutes": 5}


@pytest.mark.asyncio
async def test_book_appointment_saga_write_outbox_raises_when_appointment_missing():
    saga = FakeSagaOrchestrator(
        session=FakeSession(),
        cache=FakeCache(),
        lock_manager=FakeLockManager(),
        appointment_repo=FakeRepo(),
        doctor_client=FakeDoctorClient(),
        event_publisher=FakePublisher(),
        pricing_policy=FakePricingPolicy(),
    )

    with pytest.raises(NonRetryableError):
        await saga.execute_write_outbox({"appointment_id": str(uuid4()), "type_config": {"amount": 1}})


@pytest.mark.asyncio
async def test_book_appointment_saga_write_outbox_handles_invalid_and_non_positive_amount():
    saga = FakeSagaOrchestrator(
        session=FakeSession(),
        cache=FakeCache(),
        lock_manager=FakeLockManager(),
        appointment_repo=FakeRepo(),
        doctor_client=FakeDoctorClient(),
        event_publisher=FakePublisher(),
        pricing_policy=FakePricingPolicy(),
    )

    ctx = {
        "patient_id": str(uuid4()),
        "doctor_id": str(uuid4()),
        "specialty_id": str(uuid4()),
        "appointment_date": str(date(2026, 3, 30)),
        "start_time": str(time(10, 0)),
        "end_time": str(time(10, 30)),
        "appointment_type": "general",
        "type_config": {"price": "not-a-number"},
    }
    appt = await saga.execute_create_appointment(ctx)
    ctx["appointment_id"] = str(appt.id)

    await saga.execute_write_outbox(ctx)
    assert saga.event_publisher.calls[0]["payload"]["amount"] == 150000

    saga.event_publisher.calls.clear()
    ctx["type_config"] = {"amount": -100}
    await saga.execute_write_outbox(ctx)
    assert saga.event_publisher.calls[0]["payload"]["amount"] == 150000


@pytest.mark.asyncio
async def test_book_appointment_saga_compensate_cancel_updates_appointment_fields():
    repo = FakeRepo()
    saga = FakeSagaOrchestrator(
        session=FakeSession(),
        cache=FakeCache(),
        lock_manager=FakeLockManager(),
        appointment_repo=repo,
        doctor_client=FakeDoctorClient(),
        event_publisher=FakePublisher(),
        pricing_policy=FakePricingPolicy(),
    )

    ctx = {
        "patient_id": str(uuid4()),
        "doctor_id": str(uuid4()),
        "specialty_id": str(uuid4()),
        "appointment_date": str(date(2026, 3, 30)),
        "start_time": str(time(10, 0)),
        "end_time": str(time(10, 30)),
        "appointment_type": "general",
    }
    appt = await saga.execute_create_appointment(ctx)
    await saga.compensate_cancel_appointment({"appointment_id": str(appt.id)})

    assert appt.status == AppointmentStatus.CANCELLED
    assert appt.payment_status == PaymentStatus.REFUNDED
    assert appt.cancel_reason == "saga_compensation"
    assert appt.cancelled_by == "system"
    assert appt.cancelled_at is not None


@pytest.mark.asyncio
async def test_book_appointment_saga_compensation_noops_without_required_context():
    lock_manager = FakeLockManager()
    saga = FakeSagaOrchestrator(
        session=FakeSession(),
        cache=FakeCache(),
        lock_manager=lock_manager,
        appointment_repo=FakeRepo(),
        doctor_client=FakeDoctorClient(),
        event_publisher=FakePublisher(),
        pricing_policy=FakePricingPolicy(),
    )

    await saga.compensate_cancel_appointment({})
    await saga.compensate_release_slot_lock({"doctor_id": str(uuid4()), "appointment_date": str(date.today())})

    assert lock_manager.released == []


@pytest.mark.asyncio
async def test_book_appointment_use_case_execute_commits_and_returns_response(monkeypatch):
    session = FakeSession()
    use_case = BookAppointmentUseCase(
        session=session,
        cache=FakeCache(),
        lock_manager=FakeLockManager(),
        appointment_repo=FakeRepo(),
        doctor_client=FakeDoctorClient(),
        event_publisher=FakePublisher(),
        pricing_policy=FakePricingPolicy(),
    )

    created = SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        specialty_id=uuid4(),
        appointment_date=date(2026, 3, 30),
        start_time=time(9, 0),
        end_time=time(9, 30),
        appointment_type="general",
        chief_complaint=None,
        note_for_doctor=None,
        status=AppointmentStatus.PENDING_PAYMENT,
        payment_status=PaymentStatus.PROCESSING,
        queue_number=None,
        started_at=None,
    )

    monkeypatch.setattr(BookAppointmentSaga, "run", AsyncMock(return_value={"create_appointment": created}))

    request = CreateAppointmentRequest(
        patient_id=uuid4(),
        doctor_id=uuid4(),
        specialty_id=uuid4(),
        appointment_date=date(2026, 3, 30),
        start_time=time(9, 0),
        appointment_type="general",
    )

    result = await use_case.execute(request)

    assert result.id == created.id
    assert session.commits == 1
