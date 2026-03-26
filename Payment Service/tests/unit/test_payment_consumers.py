import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from Domain.entities.payment import Payment
from Domain.value_objects.payment_status import PaymentStatus
from infrastructure.consumers.payment_consumers import (
    PaymentExpiryConsumer,
    PaymentRefundRequestedConsumer,
    PaymentRequiredConsumer,
)


class FakeBeginCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def begin(self):
        return FakeBeginCtx()


class FakeSessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return FakeSession()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeRepo:
    def __init__(self, payment=None):
        self.payment = payment
        self.saved = []
        self.appended = []
        self.get_by_appointment_calls = []

    async def get_by_id(self, _payment_id):
        await asyncio.sleep(0)
        return self.payment

    async def get_by_appointment_id(self, appointment_id):
        await asyncio.sleep(0)
        self.get_by_appointment_calls.append(appointment_id)
        return self.payment

    async def save(self, payment):
        await asyncio.sleep(0)
        self.saved.append(payment)

    async def append_transaction(self, **kwargs):
        await asyncio.sleep(0)
        self.appended.append(kwargs)


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


def _make_payment(status=PaymentStatus.PENDING, created_at=None):
    return Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=400000,
        status=status,
        created_at=created_at or datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_payment_required_consumer_invokes_create_payment_use_case(monkeypatch):
    calls = []

    class DummyUseCase:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def execute(self, payload):
            await asyncio.sleep(0)
            calls.append(payload)

    import infrastructure.consumers.payment_consumers as consumers_module

    monkeypatch.setattr(consumers_module, "CreatePaymentFromEventUseCase", DummyUseCase)

    repo = FakeRepo()
    consumer = PaymentRequiredConsumer(
        connection=object(),
        cache=object(),
        session_factory=FakeSessionFactory(),
        payment_repo_factory=lambda _s: repo,
        payment_provider=object(),
        event_publisher=FakePublisher(),
    )

    payload = {
        "appointment_id": str(uuid4()),
        "patient_id": str(uuid4()),
        "doctor_id": str(uuid4()),
        "amount": 400000,
    }
    await consumer.handle(payload)

    assert calls == [payload]


@pytest.mark.asyncio
async def test_payment_expiry_consumer_expired_payment_marks_and_publishes():
    expired_payment = _make_payment(
        status=PaymentStatus.PENDING,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=20),
    )
    repo = FakeRepo(payment=expired_payment)
    publisher = FakePublisher()

    consumer = PaymentExpiryConsumer(
        connection=object(),
        cache=object(),
        session_factory=FakeSessionFactory(),
        payment_repo_factory=lambda _s: repo,
        event_publisher=publisher,
    )

    payload = {
        "payment_id": str(expired_payment.id),
        "appointment_id": str(expired_payment.appointment_id),
    }
    await consumer.handle(payload)

    assert expired_payment.status == PaymentStatus.EXPIRED
    assert len(repo.saved) == 1
    assert len(repo.appended) == 1
    assert repo.appended[0]["transaction_type"].value == "payment_expired"
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["event_type"] == "payment.expired"


@pytest.mark.asyncio
async def test_payment_expiry_consumer_skips_when_not_pending_or_not_expired():
    not_pending = _make_payment(status=PaymentStatus.PAID)
    repo_not_pending = FakeRepo(payment=not_pending)
    publisher = FakePublisher()

    consumer = PaymentExpiryConsumer(
        connection=object(),
        cache=object(),
        session_factory=FakeSessionFactory(),
        payment_repo_factory=lambda _s: repo_not_pending,
        event_publisher=publisher,
    )
    await consumer.handle({"payment_id": str(not_pending.id), "appointment_id": str(not_pending.appointment_id)})

    not_expired = _make_payment(status=PaymentStatus.PENDING, created_at=datetime.now(timezone.utc))
    repo_not_expired = FakeRepo(payment=not_expired)
    consumer2 = PaymentExpiryConsumer(
        connection=object(),
        cache=object(),
        session_factory=FakeSessionFactory(),
        payment_repo_factory=lambda _s: repo_not_expired,
        event_publisher=publisher,
    )
    await consumer2.handle({"payment_id": str(not_expired.id), "appointment_id": str(not_expired.appointment_id)})

    assert repo_not_pending.saved == []
    assert repo_not_pending.appended == []
    assert repo_not_expired.saved == []
    assert repo_not_expired.appended == []


@pytest.mark.asyncio
async def test_payment_refund_requested_consumer_refunds_paid_payment():
    payment = _make_payment(status=PaymentStatus.PAID)
    repo = FakeRepo(payment=payment)
    publisher = FakePublisher()

    consumer = PaymentRefundRequestedConsumer(
        connection=object(),
        cache=object(),
        session_factory=FakeSessionFactory(),
        payment_repo_factory=lambda _s: repo,
        event_publisher=publisher,
    )

    payload = {"payment_id": str(payment.id), "appointment_id": str(payment.appointment_id)}
    await consumer.handle(payload)

    assert payment.status == PaymentStatus.REFUNDED
    assert len(repo.saved) == 1
    assert len(repo.appended) == 2
    assert repo.appended[0]["transaction_type"].value == "refund_requested"
    assert repo.appended[1]["transaction_type"].value == "payment_refunded"
    assert len(publisher.calls) == 1
    assert publisher.calls[0]["event_type"] == "payment.refunded"


@pytest.mark.asyncio
async def test_payment_refund_requested_consumer_fallback_by_appointment_id():
    payment = _make_payment(status=PaymentStatus.PAID)

    class FallbackRepo(FakeRepo):
        async def get_by_id(self, _payment_id):
            await asyncio.sleep(0)
            return None

    repo = FallbackRepo(payment=payment)
    publisher = FakePublisher()
    consumer = PaymentRefundRequestedConsumer(
        connection=object(),
        cache=object(),
        session_factory=FakeSessionFactory(),
        payment_repo_factory=lambda _s: repo,
        event_publisher=publisher,
    )

    payload = {"appointment_id": str(payment.appointment_id)}
    await consumer.handle(payload)

    assert len(repo.get_by_appointment_calls) == 1
    assert len(repo.appended) == 2
    assert len(publisher.calls) == 1
