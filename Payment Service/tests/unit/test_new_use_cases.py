"""Tests for new use cases: MarkPaymentRefunded, UpdateLabFeeConfig,
ListLabFeeConfigs, GenerateLabOrderPaymentUrl."""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from Application.use_cases.generate_lab_order_payment_url import GenerateLabOrderPaymentUrlUseCase
from Application.use_cases.list_lab_fee_configs import ListLabFeeConfigsUseCase
from Application.use_cases.mark_payment_refunded import MarkPaymentRefundedUseCase
from Application.use_cases.update_lab_fee_config import UpdateLabFeeConfigUseCase
from Domain.entities.payment import Payment
from Domain.interfaces.payment_provider import PaymentResult
from Domain.value_objects.lab_fee_config import LabFeeConfig
from Domain.value_objects.payment_status import PaymentStatus


# ─────────────────────── Fakes ───────────────────────────────────────────────

class FakeSession:
    async def commit(self):
        await asyncio.sleep(0)


class FakePaymentRepo:
    def __init__(self, payment=None):
        self.payment = payment
        self.saved = []

    async def get_by_id(self, payment_id):
        await asyncio.sleep(0)
        if self.payment and self.payment.id == payment_id:
            return self.payment
        return None

    async def get_by_reference_id(self, reference_id):
        await asyncio.sleep(0)
        if self.payment and self.payment.reference_id == reference_id:
            return self.payment
        return None

    async def save(self, payment):
        await asyncio.sleep(0)
        self.saved.append(payment)
        self.payment = payment


class FakeLabFeeRepo:
    """In-memory lab fee config repository."""

    def __init__(self):
        self._store: dict[str, LabFeeConfig] = {}

    async def get_by_test_id(self, test_id: str):
        await asyncio.sleep(0)
        return self._store.get(test_id)

    async def list_all(self):
        await asyncio.sleep(0)
        return list(self._store.values())

    async def save(self, config: LabFeeConfig) -> LabFeeConfig:
        await asyncio.sleep(0)
        self._store[config.test_id] = config
        return config

    def seed(self, *configs: LabFeeConfig):
        for c in configs:
            self._store[c.test_id] = c
        return self


class FakePaymentProvider:
    def __init__(self, url: str = "https://fake-vnpay.test/pay?token=xyz"):
        self.url = url
        self.calls = []

    async def create_payment_url(self, request):
        await asyncio.sleep(0)
        self.calls.append(request)
        return self.url


class FakeEventPublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, **kwargs):
        await asyncio.sleep(0)
        self.calls.append(kwargs)


# ─────────────────────── Helpers ─────────────────────────────────────────────

def _make_payment(status=PaymentStatus.PENDING, payment_type="LAB_ORDER"):
    lab_order_id = uuid4()
    return Payment(
        id=uuid4(),
        appointment_id=None,
        patient_id=uuid4(),
        doctor_id=uuid4(),
        amount=200_000,
        payment_type=payment_type,
        reference_id=lab_order_id,
        status=status,
        created_at=datetime.now(timezone.utc),
    )


def _make_fee_config(test_id="cbc", test_name="CBC", fee=150_000):
    return LabFeeConfig(
        id=uuid4(),
        test_id=test_id,
        test_name=test_name,
        fee=fee,
    )


# ═════════════════════ MarkPaymentRefundedUseCase ════════════════════════════

class TestMarkPaymentRefunded:
    @pytest.mark.asyncio
    async def test_marks_refund_pending_as_refunded(self):
        payment = _make_payment(status=PaymentStatus.REFUND_PENDING)
        repo = FakePaymentRepo(payment)
        publisher = FakeEventPublisher()
        uc = MarkPaymentRefundedUseCase(FakeSession(), repo, publisher)

        result = await uc.execute(payment.id)

        assert repo.payment.status == PaymentStatus.REFUNDED
        assert result["payment_id"] == str(payment.id)
        assert len(repo.saved) == 1

    @pytest.mark.asyncio
    async def test_publishes_refunded_event(self):
        payment = _make_payment(status=PaymentStatus.REFUND_PENDING)
        repo = FakePaymentRepo(payment)
        publisher = FakeEventPublisher()
        uc = MarkPaymentRefundedUseCase(FakeSession(), repo, publisher)

        await uc.execute(payment.id)

        assert len(publisher.calls) == 1
        assert publisher.calls[0]["routing_key"] == "payment.refunded"
        assert publisher.calls[0]["payload"]["payment_id"] == str(payment.id)

    @pytest.mark.asyncio
    async def test_raises_if_not_refund_pending(self):
        payment = _make_payment(status=PaymentStatus.PAID)
        repo = FakePaymentRepo(payment)
        uc = MarkPaymentRefundedUseCase(FakeSession(), repo)

        with pytest.raises(PermissionError, match="not refund_pending"):
            await uc.execute(payment.id)

    @pytest.mark.asyncio
    async def test_raises_if_payment_not_found(self):
        repo = FakePaymentRepo(None)
        uc = MarkPaymentRefundedUseCase(FakeSession(), repo)

        with pytest.raises(ValueError, match="not found"):
            await uc.execute(uuid4())

    @pytest.mark.asyncio
    async def test_succeeds_without_event_publisher(self):
        payment = _make_payment(status=PaymentStatus.REFUND_PENDING)
        repo = FakePaymentRepo(payment)
        uc = MarkPaymentRefundedUseCase(FakeSession(), repo, event_publisher=None)

        result = await uc.execute(payment.id)

        assert result["payment_id"] == str(payment.id)
        assert repo.payment.status == PaymentStatus.REFUNDED


# ═════════════════════ ListLabFeeConfigsUseCase ══════════════════════════════

class TestListLabFeeConfigs:
    @pytest.mark.asyncio
    async def test_returns_all_configs_as_dicts(self):
        repo = FakeLabFeeRepo().seed(
            _make_fee_config("cbc", "CBC", 150_000),
            _make_fee_config("glucose", "Glucose", 80_000),
        )
        uc = ListLabFeeConfigsUseCase(repo)
        result = await uc.execute()

        assert isinstance(result, list)
        assert len(result) == 2
        test_ids = {r["test_id"] for r in result}
        assert test_ids == {"cbc", "glucose"}
        assert all("fee" in r for r in result)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_configs(self):
        repo = FakeLabFeeRepo()
        uc = ListLabFeeConfigsUseCase(repo)
        result = await uc.execute()

        assert result == []

    @pytest.mark.asyncio
    async def test_dict_includes_required_fields(self):
        repo = FakeLabFeeRepo().seed(_make_fee_config("cbc", "CBC", 150_000))
        uc = ListLabFeeConfigsUseCase(repo)
        result = await uc.execute()

        item = result[0]
        assert "test_id" in item
        assert "test_name" in item
        assert "fee" in item
        assert "currency" in item


# ═════════════════════ UpdateLabFeeConfigUseCase ═════════════════════════════

class TestUpdateLabFeeConfig:
    @pytest.mark.asyncio
    async def test_updates_fee_for_existing_test(self):
        repo = FakeLabFeeRepo().seed(_make_fee_config("cbc", "CBC", 150_000))
        uc = UpdateLabFeeConfigUseCase(repo)

        result = await uc.execute("cbc", 200_000)

        assert result["fee"] == 200_000
        assert result["test_id"] == "cbc"
        assert repo._store["cbc"].fee == 200_000

    @pytest.mark.asyncio
    async def test_raises_for_unknown_test_id(self):
        repo = FakeLabFeeRepo()
        uc = UpdateLabFeeConfigUseCase(repo)

        with pytest.raises(ValueError, match="not found"):
            await uc.execute("nonexistent_test", 100_000)

    @pytest.mark.asyncio
    async def test_does_not_change_test_name(self):
        repo = FakeLabFeeRepo().seed(_make_fee_config("cbc", "Complete Blood Count", 150_000))
        uc = UpdateLabFeeConfigUseCase(repo)

        result = await uc.execute("cbc", 180_000)

        assert result["test_name"] == "Complete Blood Count"

    @pytest.mark.asyncio
    async def test_returns_dict_with_all_fields(self):
        repo = FakeLabFeeRepo().seed(_make_fee_config("cbc", "CBC", 150_000))
        uc = UpdateLabFeeConfigUseCase(repo)

        result = await uc.execute("cbc", 120_000)

        assert set(result.keys()) >= {"id", "test_id", "test_name", "fee", "currency"}


# ═════════════════════ GenerateLabOrderPaymentUrlUseCase ═════════════════════

class TestGenerateLabOrderPaymentUrl:
    @pytest.mark.asyncio
    async def test_generates_url_for_pending_payment(self):
        payment = _make_payment(status=PaymentStatus.PENDING)
        repo = FakePaymentRepo(payment)
        provider = FakePaymentProvider("https://vnpay.test/pay")
        uc = GenerateLabOrderPaymentUrlUseCase(FakeSession(), repo, provider)

        result = await uc.execute(payment.reference_id)

        assert result["payment_url"] == "https://vnpay.test/pay"
        assert result["lab_order_id"] == str(payment.reference_id)
        assert result["amount"] == payment.amount
        assert result["payment_id"] == str(payment.id)

    @pytest.mark.asyncio
    async def test_generates_url_for_expired_payment(self):
        payment = _make_payment(status=PaymentStatus.EXPIRED)
        repo = FakePaymentRepo(payment)
        provider = FakePaymentProvider()
        uc = GenerateLabOrderPaymentUrlUseCase(FakeSession(), repo, provider)

        result = await uc.execute(payment.reference_id)

        assert result["payment_url"] == provider.url

    @pytest.mark.asyncio
    async def test_resets_status_to_pending_after_url_generation(self):
        payment = _make_payment(status=PaymentStatus.EXPIRED)
        repo = FakePaymentRepo(payment)
        provider = FakePaymentProvider()
        uc = GenerateLabOrderPaymentUrlUseCase(FakeSession(), repo, provider)

        await uc.execute(payment.reference_id)

        assert repo.payment.status == PaymentStatus.PENDING

    @pytest.mark.asyncio
    async def test_raises_if_payment_not_found(self):
        repo = FakePaymentRepo(None)
        provider = FakePaymentProvider()
        uc = GenerateLabOrderPaymentUrlUseCase(FakeSession(), repo, provider)

        with pytest.raises(ValueError, match="not found"):
            await uc.execute(uuid4())

    @pytest.mark.asyncio
    async def test_raises_if_payment_already_paid(self):
        payment = _make_payment(status=PaymentStatus.PAID)
        repo = FakePaymentRepo(payment)
        provider = FakePaymentProvider()
        uc = GenerateLabOrderPaymentUrlUseCase(FakeSession(), repo, provider)

        with pytest.raises(PermissionError, match="paid"):
            await uc.execute(payment.reference_id)

    @pytest.mark.asyncio
    async def test_raises_if_payment_refund_pending(self):
        payment = _make_payment(status=PaymentStatus.REFUND_PENDING)
        repo = FakePaymentRepo(payment)
        provider = FakePaymentProvider()
        uc = GenerateLabOrderPaymentUrlUseCase(FakeSession(), repo, provider)

        with pytest.raises(PermissionError, match="refund_pending"):
            await uc.execute(payment.reference_id)

    @pytest.mark.asyncio
    async def test_saves_payment_url_on_entity(self):
        payment = _make_payment(status=PaymentStatus.PENDING)
        repo = FakePaymentRepo(payment)
        provider = FakePaymentProvider("https://vnpay.test/pay?order=123")
        uc = GenerateLabOrderPaymentUrlUseCase(FakeSession(), repo, provider)

        await uc.execute(payment.reference_id)

        assert repo.payment.payment_url == "https://vnpay.test/pay?order=123"

    @pytest.mark.asyncio
    async def test_calls_provider_with_correct_amount(self):
        payment = _make_payment(status=PaymentStatus.PENDING)
        payment.amount = 350_000
        repo = FakePaymentRepo(payment)
        provider = FakePaymentProvider()
        uc = GenerateLabOrderPaymentUrlUseCase(FakeSession(), repo, provider)

        await uc.execute(payment.reference_id)

        assert len(provider.calls) == 1
        assert provider.calls[0].amount == 350_000
