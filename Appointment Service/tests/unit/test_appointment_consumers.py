import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from healthai_events.exceptions import RetryableError
from infrastructure.consumers.appointment_timeout_consumer import AppointmentTimeoutConsumer
from infrastructure.consumers.payment_consumers import PaymentPaidConsumer, _cancel_for_payment


class FakeBegin:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def begin(self):
        return FakeBegin()


class SessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __init__(self):
        self.session = FakeSession()


class FakeRepo:
    def __init__(self, appt=None):
        self.appt = appt
        self.saved = []
        self.next_queue = 5

    async def get_by_id_with_lock(self, _id):
        await asyncio.sleep(0)
        return self.appt

    async def get_next_queue_number(self, *_args):
        await asyncio.sleep(0)
        return self.next_queue

    async def save(self, appt):
        await asyncio.sleep(0)
        self.saved.append(appt)


class FakeDoctorClient:
    def __init__(self, cfg=None, fail=False):
        self.cfg = cfg
        self.fail = fail

    async def get_doctor(self, _doctor_id):
        await asyncio.sleep(0)
        if self.fail:
            raise RuntimeError("doctor svc down")
        return self.cfg


def _appt(status=AppointmentStatus.PENDING_PAYMENT, payment_status=PaymentStatus.UNPAID):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        appointment_date=now.date(),
        start_time=now.time().replace(microsecond=0),
        status=status,
        payment_status=payment_status,
        queue_number=None,
        confirmed_at=None,
        cancelled_at=None,
        cancelled_by=None,
        cancel_reason=None,
    )


@pytest.mark.asyncio
async def test_payment_paid_consumer_missing_id_raises():
    consumer = PaymentPaidConsumer(
        connection=object(),
        cache=object(),
        session_factory=SessionFactory(),
        appointment_repo_factory=lambda _s: FakeRepo(),
        doctor_client=FakeDoctorClient(cfg={"auto_confirm": True}),
    )

    with pytest.raises(ValueError):
        await consumer.handle({})


@pytest.mark.asyncio
async def test_payment_paid_consumer_auto_confirm_true(monkeypatch):
    appt = _appt()
    repo = FakeRepo(appt=appt)
    writes = []

    async def fake_write(session, **kwargs):
        await asyncio.sleep(0)
        writes.append(kwargs)

    import infrastructure.consumers.payment_consumers as module

    monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

    consumer = PaymentPaidConsumer(
        connection=object(),
        cache=object(),
        session_factory=SessionFactory(),
        appointment_repo_factory=lambda _s: repo,
        doctor_client=FakeDoctorClient(cfg={"auto_confirm": True}),
    )

    await consumer.handle({"appointment_id": str(appt.id)})

    assert appt.status == AppointmentStatus.CONFIRMED
    assert appt.payment_status == PaymentStatus.PAID
    assert len(repo.saved) == 1
    assert any(w["event_type"] == "appointment.confirmed" for w in writes)
    assert any(w["event_type"] == "cache.invalidate" for w in writes)


@pytest.mark.asyncio
async def test_payment_paid_consumer_auto_confirm_false(monkeypatch):
    appt = _appt()
    repo = FakeRepo(appt=appt)
    writes = []

    async def fake_write(session, **kwargs):
        await asyncio.sleep(0)
        writes.append(kwargs)

    import infrastructure.consumers.payment_consumers as module

    monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

    consumer = PaymentPaidConsumer(
        connection=object(),
        cache=object(),
        session_factory=SessionFactory(),
        appointment_repo_factory=lambda _s: repo,
        doctor_client=FakeDoctorClient(cfg={"auto_confirm": False, "confirmation_timeout_minutes": 10}),
    )

    await consumer.handle({"appointment_id": str(appt.id)})

    assert appt.status == AppointmentStatus.PENDING
    assert any(w["event_type"] == "appointment.created" for w in writes)
    assert any(w["event_type"] == "appointment.check_timeout" for w in writes)


@pytest.mark.asyncio
async def test_cancel_for_payment_paths(monkeypatch):
    with pytest.raises(ValueError):
        await _cancel_for_payment(SessionFactory(), lambda _s: FakeRepo(), {}, "payment_failed")

    writes = []

    async def fake_write(session, **kwargs):
        await asyncio.sleep(0)
        writes.append(kwargs)

    import infrastructure.consumers.payment_consumers as module

    monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

    # not found
    await _cancel_for_payment(
        SessionFactory(), lambda _s: FakeRepo(appt=None), {"appointment_id": str(uuid4())}, "payment_failed"
    )

    # status mismatch
    not_pending = _appt(status=AppointmentStatus.CONFIRMED)
    await _cancel_for_payment(
        SessionFactory(),
        lambda _s: FakeRepo(appt=not_pending),
        {"appointment_id": str(not_pending.id)},
        "payment_failed",
    )

    # pending payment -> cancelled
    pending = _appt(status=AppointmentStatus.PENDING_PAYMENT)
    repo = FakeRepo(appt=pending)
    await _cancel_for_payment(
        SessionFactory(),
        lambda _s: repo,
        {"appointment_id": str(pending.id)},
        "payment_failed",
    )

    assert pending.status == AppointmentStatus.CANCELLED
    assert pending.payment_status == PaymentStatus.UNPAID
    assert len(repo.saved) == 1
    assert any(w["event_type"] == "appointment.cancelled" for w in writes)
    assert any(w["event_type"] == "cache.invalidate" for w in writes)


@pytest.mark.asyncio
async def test_appointment_timeout_consumer_early_and_paid_refund(monkeypatch):
    writes = []

    async def fake_write(session, **kwargs):
        await asyncio.sleep(0)
        writes.append(kwargs)

    import infrastructure.consumers.appointment_timeout_consumer as module

    monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

    appt = _appt(status=AppointmentStatus.PENDING, payment_status=PaymentStatus.PAID)
    repo = FakeRepo(appt=appt)

    consumer = AppointmentTimeoutConsumer(
        connection=object(),
        cache=object(),
        session_factory=SessionFactory(),
        appointment_repo_factory=lambda _s: repo,
    )

    future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    with pytest.raises(RetryableError):
        await consumer.handle({"appointment_id": str(appt.id), "timeout_at": future})

    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await consumer.handle({"appointment_id": str(appt.id), "timeout_at": past})

    assert appt.status == AppointmentStatus.CANCELLED
    assert appt.payment_status == PaymentStatus.REFUNDED
    assert any(w["event_type"] == "payment.refund_requested" for w in writes)
