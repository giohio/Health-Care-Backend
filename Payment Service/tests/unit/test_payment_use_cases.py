import asyncio
from datetime import date
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from Application.use_cases.create_lab_order_payment import CreateLabOrderPaymentUseCase
from Application.use_cases.create_payment import CreatePaymentFromEventUseCase
from Application.use_cases.handle_vnpay_ipn import ProcessVNPayIPnUseCase
from Application.use_cases.list_admin_payment_history import ListAdminPaymentHistoryUseCase
from Application.use_cases.list_patient_payment_history import ListPatientPaymentHistoryUseCase
from Application.use_cases.process_vnpay_ipn import GetPaymentUseCase
from Domain.entities.payment import Payment
from Domain.entities.payment_transaction import PaymentTransaction
from Domain.interfaces.payment_provider import PaymentResult
from Domain.value_objects.payment_status import PaymentStatus
from Domain.value_objects.payment_transaction_type import PaymentTransactionType


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        await asyncio.sleep(0)
        self.commits += 1


class FakeRepo:
    def __init__(self, payment=None):
        self.payment = payment
        self.saved = []
        self.appended = []
        self.transactions = []
        self.patient_history_calls = []
        self.admin_history_calls = []
        self.history_items = []
        self.history_total = 0

    async def save(self, payment):
        await asyncio.sleep(0)
        self.saved.append(payment)
        self.payment = payment

    async def append_transaction(self, **kwargs):
        await asyncio.sleep(0)
        self.appended.append(kwargs)
        txn = PaymentTransaction(
            id=uuid4(),
            payment_id=kwargs["payment_id"],
            appointment_id=kwargs["appointment_id"],
            transaction_type=kwargs["transaction_type"],
            amount=kwargs["amount"],
            currency=kwargs.get("currency", "VND"),
            provider_ref=kwargs.get("provider_ref"),
            response_code=kwargs.get("response_code"),
            metadata=kwargs.get("metadata"),
            created_at=datetime.now(timezone.utc),
        )
        self.transactions.append(txn)
        return txn

    async def get_by_vnpay_txn_ref(self, txn_ref):
        await asyncio.sleep(0)
        if self.payment and self.payment.vnpay_txn_ref == txn_ref:
            return self.payment
        return None

    async def get_by_appointment_id(self, appointment_id):
        await asyncio.sleep(0)
        if self.payment and self.payment.appointment_id == appointment_id:
            return self.payment
        return None

    async def list_transactions(self, _payment_id):
        await asyncio.sleep(0)
        return self.transactions

    async def list_history_by_patient_id(self, patient_id, **filters):
        await asyncio.sleep(0)
        self.patient_history_calls.append((patient_id, filters))
        return self.history_items, self.history_total

    async def list_history(self, **filters):
        await asyncio.sleep(0)
        self.admin_history_calls.append(filters)
        return self.history_items, self.history_total

    async def update_appointment_status(self, appointment_id, appointment_status):
        await asyncio.sleep(0)
        self.update_appt_status_calls = getattr(self, "update_appt_status_calls", [])
        self.update_appt_status_calls.append((appointment_id, appointment_status))


class FakeProvider:
    def __init__(self, verify_result=None):
        self.verify_result = verify_result or PaymentResult(success=True, provider_ref="PREF-1")
        self.create_calls = []
        self.verify_calls = []

    async def create_payment_url(self, request):
        await asyncio.sleep(0)
        self.create_calls.append(request)
        return "https://pay.test/checkout"

    def verify_callback(self, params):
        self.verify_calls.append(params)
        return self.verify_result


class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


def _payload():
    return {
        "appointment_id": str(uuid4()),
        "patient_id": str(uuid4()),
        "doctor_id": str(uuid4()),
        "amount": 650000,
    }


@pytest.mark.asyncio
async def test_create_payment_from_event_saves_payment_and_emits_events():
    repo = FakeRepo()
    provider = FakeProvider()
    publisher = FakePublisher()
    session = FakeSession()

    use_case = CreatePaymentFromEventUseCase(
        session=session, payment_repo=repo, payment_provider=provider, event_publisher=publisher
    )
    payment = await use_case.execute(_payload())

    assert payment.status == PaymentStatus.PENDING
    assert payment.payment_url == "https://pay.test/checkout"
    assert payment.vnpay_txn_ref and "-" in payment.vnpay_txn_ref  # UUID format with dashes
    assert len(repo.saved) == 1
    assert len(repo.appended) == 1
    assert repo.appended[0]["transaction_type"] == PaymentTransactionType.PAYMENT_CREATED
    assert [c["event_type"] for c in publisher.calls] == ["payment.created", "payment.check_expiry"]


@pytest.mark.asyncio
async def test_create_lab_order_payment_saves_lab_payment_and_emits_events():
    repo = FakeRepo()
    provider = FakeProvider()
    publisher = FakePublisher()
    session = FakeSession()
    lab_order_id = uuid4()
    patient_id = uuid4()
    doctor_id = uuid4()

    use_case = CreateLabOrderPaymentUseCase(
        session=session,
        payment_repo=repo,
        payment_provider=provider,
        event_publisher=publisher,
    )

    payment = await use_case.execute(
        {
            "lab_order_id": str(lab_order_id),
            "patient_id": str(patient_id),
            "doctor_id": str(doctor_id),
            "amount": 275000,
            "test_name": "Lipid Panel",
        }
    )

    assert payment.payment_type == "LAB_ORDER"
    assert payment.reference_id == lab_order_id
    assert payment.appointment_id is None
    assert payment.vnpay_txn_ref == f"LAB_{lab_order_id}"
    assert payment.payment_url == "https://pay.test/checkout"
    assert repo.appended[0]["appointment_id"] is None
    assert repo.appended[0]["metadata"]["lab_order_id"] == str(lab_order_id)
    assert [call["event_type"] for call in publisher.calls] == ["payment.created", "payment.check_expiry"]
    assert publisher.calls[0]["payload"]["payment_type"] == "LAB_ORDER"
    assert publisher.calls[0]["payload"]["lab_order_id"] == str(lab_order_id)


@pytest.mark.asyncio
async def test_process_ipn_invalid_signature_returns_97():
    payment = Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=500000,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    payment.vnpay_txn_ref = "APPX"
    repo = FakeRepo(payment=payment)
    provider = FakeProvider(
        verify_result=PaymentResult(success=False, provider_ref=None, failure_reason="Invalid signature")
    )
    publisher = FakePublisher()
    session = FakeSession()

    use_case = ProcessVNPayIPnUseCase(
        session=session, payment_repo=repo, payment_provider=provider, event_publisher=publisher
    )
    result = await use_case.execute({"vnp_TxnRef": "APPX"})

    assert result["RspCode"] == "97"
    assert repo.saved == []
    assert publisher.calls == []


@pytest.mark.asyncio
async def test_process_ipn_missing_txn_ref_returns_01():
    repo = FakeRepo()
    provider = FakeProvider(verify_result=PaymentResult(success=True, provider_ref="PR"))
    use_case = ProcessVNPayIPnUseCase(
        session=FakeSession(), payment_repo=repo, payment_provider=provider, event_publisher=FakePublisher()
    )

    result = await use_case.execute({"vnp_ResponseCode": "00"})

    assert result["RspCode"] == "01"


@pytest.mark.asyncio
async def test_process_ipn_payment_not_found_returns_01():
    repo = FakeRepo(payment=None)
    provider = FakeProvider(verify_result=PaymentResult(success=True, provider_ref="PR"))
    use_case = ProcessVNPayIPnUseCase(
        session=FakeSession(), payment_repo=repo, payment_provider=provider, event_publisher=FakePublisher()
    )

    result = await use_case.execute({"vnp_TxnRef": "UNKNOWN", "vnp_ResponseCode": "00"})

    assert result["RspCode"] == "01"


@pytest.mark.asyncio
async def test_process_ipn_success_marks_paid_and_publishes_paid_event():
    payment = Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=500000,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    payment.vnpay_txn_ref = "APPPAID"
    repo = FakeRepo(payment=payment)
    provider = FakeProvider(verify_result=PaymentResult(success=True, provider_ref="TRANS-1"))
    publisher = FakePublisher()
    session = FakeSession()
    use_case = ProcessVNPayIPnUseCase(
        session=session, payment_repo=repo, payment_provider=provider, event_publisher=publisher
    )

    result = await use_case.execute({"vnp_TxnRef": "APPPAID", "vnp_ResponseCode": "00"})

    assert result == {"RspCode": "00", "Message": "OK"}
    assert payment.status == PaymentStatus.PAID
    assert len(repo.saved) == 1
    assert repo.appended[-1]["transaction_type"] == PaymentTransactionType.PAYMENT_PAID
    assert publisher.calls[-1]["event_type"] == "payment.paid"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_process_ipn_success_for_lab_order_publishes_lab_payment_paid():
    lab_order_id = uuid4()
    payment = Payment(
        id=uuid4(),
        appointment_id=None,
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=500000,
        payment_type="LAB_ORDER",
        reference_id=lab_order_id,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    payment.vnpay_txn_ref = f"LAB_{lab_order_id}"
    repo = FakeRepo(payment=payment)
    provider = FakeProvider(verify_result=PaymentResult(success=True, provider_ref="TRANS-LAB-1"))
    publisher = FakePublisher()
    session = FakeSession()

    use_case = ProcessVNPayIPnUseCase(
        session=session, payment_repo=repo, payment_provider=provider, event_publisher=publisher
    )

    result = await use_case.execute({"vnp_TxnRef": payment.vnpay_txn_ref, "vnp_ResponseCode": "00"})

    assert result == {"RspCode": "00", "Message": "OK"}
    assert payment.status == PaymentStatus.PAID
    assert publisher.calls[-1]["event_type"] == "lab_payment.paid"
    assert publisher.calls[-1]["payload"]["lab_order_id"] == str(lab_order_id)
    assert publisher.calls[-1]["payload"]["provider_ref"] == "TRANS-LAB-1"


@pytest.mark.asyncio
async def test_process_ipn_failed_marks_failed_and_publishes_failed_event():
    payment = Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=500000,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    payment.vnpay_txn_ref = "APPFAIL"
    repo = FakeRepo(payment=payment)
    provider = FakeProvider(verify_result=PaymentResult(success=True, provider_ref="TRANS-2"))
    publisher = FakePublisher()
    session = FakeSession()
    use_case = ProcessVNPayIPnUseCase(
        session=session, payment_repo=repo, payment_provider=provider, event_publisher=publisher
    )

    result = await use_case.execute({"vnp_TxnRef": "APPFAIL", "vnp_ResponseCode": "24"})

    assert result == {"RspCode": "00", "Message": "Processed failed payment"}
    assert payment.status == PaymentStatus.FAILED
    assert repo.appended[-1]["transaction_type"] == PaymentTransactionType.PAYMENT_FAILED
    assert publisher.calls[-1]["event_type"] == "payment.failed"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_get_payment_use_case_success_returns_transactions_payload():
    payment = Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=500000,
        status=PaymentStatus.PAID,
        created_at=datetime.now(timezone.utc),
    )
    payment.payment_url = "https://pay.test/checkout"
    payment.vnpay_txn_ref = "APPDATA"

    txn = SimpleNamespace(
        id=uuid4(),
        transaction_type=PaymentTransactionType.PAYMENT_PAID,
        amount=500000,
        currency="VND",
        provider_ref="TRANS-X",
        response_code="00",
        metadata={"ipn": True},
        created_at=datetime.now(timezone.utc),
    )
    repo = FakeRepo(payment=payment)
    repo.transactions = [txn]

    use_case = GetPaymentUseCase(payment_repo=repo)
    result = await use_case.execute(payment.appointment_id)

    assert result["status"] == "paid"
    assert result["transactions"][0]["transaction_type"] == "payment_paid"


@pytest.mark.asyncio
async def test_get_payment_use_case_not_found_raises_value_error():
    repo = FakeRepo(payment=None)
    use_case = GetPaymentUseCase(payment_repo=repo)

    with pytest.raises(ValueError, match="Payment not found"):
        await use_case.execute(uuid4())


@pytest.mark.asyncio
async def test_list_patient_payment_history_use_case_returns_paginated_result():
    payment = Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=500000,
        status=PaymentStatus.PAID,
        created_at=datetime.now(timezone.utc),
    )
    repo = FakeRepo()
    repo.history_items = [payment]
    repo.history_total = 21

    use_case = ListPatientPaymentHistoryUseCase(repo)
    result = await use_case.execute(
        payment.patient_id,
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 5),
        status=PaymentStatus.PAID,
        page=2,
        limit=10,
    )

    assert result.total == 21
    assert result.total_pages == 3
    assert result.items[0].id == str(payment.id)
    patient_id, filters = repo.patient_history_calls[-1]
    assert patient_id == payment.patient_id
    assert filters["offset"] == 10
    assert filters["limit"] == 10


@pytest.mark.asyncio
async def test_list_admin_payment_history_use_case_includes_owner_fields():
    payment = Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=700000,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    repo = FakeRepo()
    repo.history_items = [payment]
    repo.history_total = 1

    use_case = ListAdminPaymentHistoryUseCase(repo)
    result = await use_case.execute(
        patient_id=payment.patient_id,
        doctor_id=payment.doctor_id,
        page=1,
        limit=50,
    )

    assert result.total == 1
    assert result.items[0].patient_id == str(payment.patient_id)
    assert result.items[0].doctor_id == str(payment.doctor_id)
    filters = repo.admin_history_calls[-1]
    assert filters["patient_id"] == payment.patient_id
    assert filters["doctor_id"] == payment.doctor_id


@pytest.mark.asyncio
async def test_list_payment_history_use_case_rejects_invalid_date_range():
    repo = FakeRepo()
    use_case = ListPatientPaymentHistoryUseCase(repo)

    with pytest.raises(ValueError, match="from_date"):
        await use_case.execute(
            uuid4(),
            from_date=date(2026, 4, 5),
            to_date=date(2026, 4, 1),
        )


@pytest.mark.asyncio
async def test_appointment_status_is_included_in_history_item():
    """serialize_payment() must carry appointment_status from the Payment entity."""
    from Application.use_cases.payment_history_models import serialize_payment

    payment = Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=300000,
        status=PaymentStatus.PENDING,
        appointment_status="cancelled",
        created_at=datetime.now(timezone.utc),
    )
    item = serialize_payment(payment)
    assert item.appointment_status == "cancelled"


@pytest.mark.asyncio
async def test_appointment_status_defaults_to_pending_payment():
    """Payment entity default appointment_status is 'pending_payment'."""
    payment = Payment(
        id=uuid4(),
        appointment_id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=300000,
        status=PaymentStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    assert payment.appointment_status == "pending_payment"


@pytest.mark.asyncio
async def test_appt_status_consumer_calls_update_on_matching_event():
    """Consumer's handle() must call repo.update_appointment_status with correct value."""
    from infrastructure.consumers.payment_consumers import _appt_status_consumer_class

    appointment_id = uuid4()
    captured = []

    class FakeRepoForConsumer:
        async def update_appointment_status(self, appt_id, status):
            captured.append((appt_id, status))

    sessions_entered = []

    class FakeSessionCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def begin(self):
            return self

    def fake_session_factory():
        s = FakeSessionCtx()
        sessions_entered.append(s)
        return s

    def fake_repo_factory(session):
        return FakeRepoForConsumer()

    consumer_cls = _appt_status_consumer_class("cancelled", "cancelled")
    consumer = consumer_cls.__new__(consumer_cls)
    consumer._session_factory = fake_session_factory
    consumer._payment_repo_factory = fake_repo_factory

    await consumer.handle({"appointment_id": str(appointment_id)})

    assert len(captured) == 1
    assert captured[0] == (appointment_id, "cancelled")


@pytest.mark.asyncio
async def test_appt_status_consumer_ignores_missing_appointment_id():
    """Consumer's handle() must be a no-op when appointment_id is absent."""
    from infrastructure.consumers.payment_consumers import _appt_status_consumer_class

    consumer_cls = _appt_status_consumer_class("confirmed", "confirmed")
    consumer = consumer_cls.__new__(consumer_cls)
    consumer._session_factory = lambda: None  # would raise if called
    consumer._payment_repo_factory = lambda s: None

    # Should not raise
    await consumer.handle({})  # no appointment_id key
