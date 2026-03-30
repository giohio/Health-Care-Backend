import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from Application.use_cases.create_payment import CreatePaymentFromEventUseCase
from Application.use_cases.handle_vnpay_ipn import ProcessVNPayIPnUseCase
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
