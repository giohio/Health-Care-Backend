"""Tests for LabOrderCancelledConsumer."""
import asyncio
from uuid import uuid4

import pytest
from Domain.entities.payment import Payment
from Domain.value_objects.payment_status import PaymentStatus
from infrastructure.consumers.lab_order_cancelled_consumer import LabOrderCancelledConsumer
from datetime import datetime, timezone


# ─────────────────────── Fakes ───────────────────────────────────────────────

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

    async def get_by_reference_id(self, reference_id):
        await asyncio.sleep(0)
        if self.payment and self.payment.reference_id == reference_id:
            return self.payment
        return None

    async def save(self, payment):
        await asyncio.sleep(0)
        self.saved.append(payment)
        self.payment = payment


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


def _make_consumer(repo, publisher=None, session_factory=None):
    sf = session_factory or FakeSessionFactory()
    return LabOrderCancelledConsumer(
        connection=None,
        cache=None,
        session_factory=sf,
        payment_repo_factory=lambda session: repo,
        event_publisher=publisher,
    )


def _make_paid_payment(lab_order_id=None):
    return Payment(
        id=uuid4(),
        appointment_id=None,
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=150_000,
        payment_type="LAB_ORDER",
        reference_id=lab_order_id or uuid4(),
        status=PaymentStatus.PAID,
        created_at=datetime.now(timezone.utc),
    )


# ─────────────────────── Tests ───────────────────────────────────────────────

class TestLabOrderCancelledConsumer:
    @pytest.mark.asyncio
    async def test_marks_paid_payment_as_refund_pending(self):
        lab_order_id = uuid4()
        payment = _make_paid_payment(lab_order_id)
        repo = FakeRepo(payment)
        consumer = _make_consumer(repo)

        await consumer.handle({"lab_order_id": str(lab_order_id)})

        assert repo.payment.status == PaymentStatus.REFUND_PENDING
        assert len(repo.saved) == 1

    @pytest.mark.asyncio
    async def test_publishes_refund_pending_event(self):
        lab_order_id = uuid4()
        payment = _make_paid_payment(lab_order_id)
        repo = FakeRepo(payment)
        publisher = FakePublisher()
        consumer = _make_consumer(repo, publisher)

        await consumer.handle({"lab_order_id": str(lab_order_id)})

        assert len(publisher.calls) == 1
        assert publisher.calls[0]["routing_key"] == "payment.refund_pending"
        assert publisher.calls[0]["payload"]["lab_order_id"] == str(lab_order_id)

    @pytest.mark.asyncio
    async def test_skips_non_paid_payment(self):
        lab_order_id = uuid4()
        payment = _make_paid_payment(lab_order_id)
        payment.status = PaymentStatus.PENDING  # Not paid
        repo = FakeRepo(payment)
        publisher = FakePublisher()
        consumer = _make_consumer(repo, publisher)

        await consumer.handle({"lab_order_id": str(lab_order_id)})

        assert repo.payment.status == PaymentStatus.PENDING
        assert len(repo.saved) == 0
        assert len(publisher.calls) == 0

    @pytest.mark.asyncio
    async def test_ignores_missing_lab_order_id(self):
        repo = FakeRepo(None)
        consumer = _make_consumer(repo)

        # Should not raise
        await consumer.handle({})
        assert len(repo.saved) == 0

    @pytest.mark.asyncio
    async def test_ignores_invalid_lab_order_id(self):
        repo = FakeRepo(None)
        consumer = _make_consumer(repo)

        await consumer.handle({"lab_order_id": "not-a-valid-uuid"})
        assert len(repo.saved) == 0

    @pytest.mark.asyncio
    async def test_does_nothing_if_payment_not_found(self):
        repo = FakeRepo(None)  # no payment stored
        publisher = FakePublisher()
        consumer = _make_consumer(repo, publisher)

        await consumer.handle({"lab_order_id": str(uuid4())})

        assert len(repo.saved) == 0
        assert len(publisher.calls) == 0

    @pytest.mark.asyncio
    async def test_handles_string_uuid(self):
        """Accept both string and UUID for lab_order_id."""
        lab_order_id = uuid4()
        payment = _make_paid_payment(lab_order_id)
        repo = FakeRepo(payment)
        consumer = _make_consumer(repo)

        await consumer.handle({"lab_order_id": str(lab_order_id)})

        assert repo.payment.status == PaymentStatus.REFUND_PENDING

    @pytest.mark.asyncio
    async def test_gracefully_handles_missing_session_factory(self):
        """No crash when session_factory is None."""
        repo = FakeRepo(None)
        consumer = LabOrderCancelledConsumer(
            connection=None,
            cache=None,
            session_factory=None,
            payment_repo_factory=None,
            event_publisher=None,
        )

        # Should log warning but not raise
        await consumer.handle({"lab_order_id": str(uuid4())})
