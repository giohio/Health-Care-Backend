import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from Domain.entities.payment import Payment
from Domain.value_objects.payment_status import PaymentStatus
from Domain.value_objects.payment_transaction_type import PaymentTransactionType
from infrastructure.database.models import PaymentModel, PaymentTransactionModel
from infrastructure.repositories.payment_repository import PaymentRepository


class FakeScalars:
    def __init__(self, items):
        self._items = items

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class FakeExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return FakeScalars(self._items)


class FakeSession:
    def __init__(self):
        self.added = []
        self.flush_count = 0
        self.get_result = None
        self.execute_results = []
        self.executed_statements = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        await asyncio.sleep(0)
        self.flush_count += 1

    async def get(self, _model, _id):
        await asyncio.sleep(0)
        return self.get_result

    async def execute(self, stmt):
        await asyncio.sleep(0)
        self.executed_statements.append(stmt)
        return self.execute_results.pop(0)


def _make_payment():
    return Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=500000,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )


def _make_payment_model(payment: Payment):
    return PaymentModel(
        id=payment.id,
        appointment_id=payment.appointment_id,
        patient_id=payment.patient_id,
        doctor_id=payment.doctor_id,
        amount=payment.amount,
        currency=payment.currency,
        status=payment.status,
        vnpay_txn_ref=payment.vnpay_txn_ref,
        vnpay_provider_ref=payment.vnpay_provider_ref,
        payment_url=payment.payment_url,
        paid_at=payment.paid_at,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


@pytest.mark.asyncio
async def test_save_creates_new_model_when_missing(monkeypatch):
    session = FakeSession()
    repo = PaymentRepository(session)
    payment = _make_payment()

    async def _missing(_payment_id):
        await asyncio.sleep(0)
        return None

    monkeypatch.setattr(repo, "_find_model", _missing)

    await repo.save(payment)

    assert session.flush_count == 1
    assert len(session.added) == 1
    created = session.added[0]
    assert isinstance(created, PaymentModel)
    assert created.id == payment.id
    assert created.amount == payment.amount


@pytest.mark.asyncio
async def test_save_updates_existing_model(monkeypatch):
    session = FakeSession()
    repo = PaymentRepository(session)
    payment = _make_payment()
    payment.mark_as_paid(provider_ref="PREF-1", paid_at=datetime.now(timezone.utc))
    payment.payment_url = "https://pay.test/u"

    existing = _make_payment_model(_make_payment())

    async def _found(_payment_id):
        await asyncio.sleep(0)
        return existing

    monkeypatch.setattr(repo, "_find_model", _found)

    await repo.save(payment)

    assert session.flush_count == 1
    assert session.added == []
    assert existing.status == PaymentStatus.PAID
    assert existing.vnpay_provider_ref == "PREF-1"
    assert existing.payment_url == "https://pay.test/u"
    assert existing.paid_at is not None


@pytest.mark.asyncio
async def test_get_by_id_found_and_not_found(monkeypatch):
    session = FakeSession()
    repo = PaymentRepository(session)
    payment = _make_payment()
    model = _make_payment_model(payment)

    async def _found(_payment_id):
        await asyncio.sleep(0)
        return model

    monkeypatch.setattr(repo, "_find_model", _found)
    entity = await repo.get_by_id(payment.id)
    assert entity is not None
    assert entity.id == payment.id
    assert entity.status == PaymentStatus.PENDING

    async def _missing(_payment_id):
        await asyncio.sleep(0)
        return None

    monkeypatch.setattr(repo, "_find_model", _missing)
    entity_none = await repo.get_by_id(uuid4())
    assert entity_none is None


@pytest.mark.asyncio
async def test_get_by_appointment_id_and_vnpay_txn_ref():
    session = FakeSession()
    repo = PaymentRepository(session)

    payment = _make_payment()
    payment.vnpay_txn_ref = "APP-REF-1"
    model = _make_payment_model(payment)

    session.execute_results = [
        FakeExecuteResult([model]),
        FakeExecuteResult([model]),
        FakeExecuteResult([]),
    ]

    found_by_appt = await repo.get_by_appointment_id(payment.appointment_id)
    found_by_ref = await repo.get_by_vnpay_txn_ref("APP-REF-1")
    not_found = await repo.get_by_vnpay_txn_ref("NOPE")

    assert found_by_appt is not None
    assert found_by_appt.appointment_id == payment.appointment_id
    assert found_by_ref is not None
    assert found_by_ref.vnpay_txn_ref == "APP-REF-1"
    assert not_found is None
    assert len(session.executed_statements) == 3


@pytest.mark.asyncio
async def test_append_transaction_and_list_transactions():
    session = FakeSession()
    repo = PaymentRepository(session)

    payment_id = uuid4()
    appointment_id = uuid4()

    created_model = PaymentTransactionModel(
        id=uuid4(),
        payment_id=payment_id,
        appointment_id=appointment_id,
        transaction_type=PaymentTransactionType.PAYMENT_CREATED,
        amount=500000,
        currency="VND",
        provider_ref="REF-1",
        response_code="00",
        metadata_json={"source": "test"},
        created_at=datetime.now(timezone.utc),
    )

    async def _fake_flush_assign_model():
        await asyncio.sleep(0)
        session.flush_count += 1
        if session.added:
            added = session.added[-1]
            if isinstance(added, PaymentTransactionModel):
                added.id = created_model.id
                added.created_at = created_model.created_at

    session.flush = _fake_flush_assign_model

    txn = await repo.append_transaction(
        payment_id=payment_id,
        appointment_id=appointment_id,
        transaction_type=PaymentTransactionType.PAYMENT_CREATED,
        amount=500000,
        provider_ref="REF-1",
        response_code="00",
        metadata={"source": "test"},
    )

    assert txn.payment_id == payment_id
    assert txn.appointment_id == appointment_id
    assert txn.transaction_type == PaymentTransactionType.PAYMENT_CREATED

    listed_model = PaymentTransactionModel(
        id=uuid4(),
        payment_id=payment_id,
        appointment_id=appointment_id,
        transaction_type=PaymentTransactionType.PAYMENT_PAID,
        amount=500000,
        currency="VND",
        provider_ref="REF-2",
        response_code="00",
        metadata_json={"ipn": True},
        created_at=datetime.now(timezone.utc),
    )
    session.execute_results = [FakeExecuteResult([listed_model])]

    items = await repo.list_transactions(payment_id)
    assert len(items) == 1
    assert items[0].transaction_type == PaymentTransactionType.PAYMENT_PAID
    assert items[0].metadata == {"ipn": True}
