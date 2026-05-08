"""Tests for DeleteLabOrderUseCase — specifically the payment-status refund logic."""
import uuid
from datetime import datetime, timezone

import pytest

from Application.use_cases.delete_lab_order import DeleteLabOrderUseCase
from Domain.entities.lab_order import LabOrder
from Domain.entities.lab_result import LabResult
from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType
from tests.conftest import FakeLabOrderRepo as _FakeLabOrderRepo
from tests.conftest import FakeLabResultRepo as _FakeLabResultRepo
from tests.conftest import make_lab_order, make_lab_result


class FakeLabOrderRepo(_FakeLabOrderRepo):
    async def delete(self, order_id) -> None:
        self._store.pop(order_id, None)


class FakeLabResultRepo(_FakeLabResultRepo):
    async def delete(self, result_id) -> None:
        self._store.pop(result_id, None)

NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


# ─────────────────────── Fake event publisher ────────────────────────────────

class FakePublisher:
    def __init__(self):
        self.calls = []

    async def publish(self, event_type: str, payload: dict):
        self.calls.append({"event_type": event_type, "payload": payload})


# ─────────────────────── Helpers ─────────────────────────────────────────────

def _make_order(payment_status="UNPAID", fee=0, **kwargs) -> LabOrder:
    return make_lab_order(payment_status=payment_status, fee=fee, **kwargs)


def _make_use_case(order_repo, result_repo, publisher=None):
    return DeleteLabOrderUseCase(
        order_repo=order_repo,
        result_repo=result_repo,
        event_publisher=publisher,
    )


# ═════════════════════ DeleteLabOrderUseCase ════════════════════════════════

class TestDeleteLabOrderUseCase:
    @pytest.mark.asyncio
    async def test_doctor_can_delete_own_order(self):
        doctor_id = uuid.uuid4()
        order = _make_order(doctor_id=doctor_id)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        result_repo = FakeLabResultRepo()
        uc = _make_use_case(order_repo, result_repo)

        await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")

        assert len(order_repo._store) == 0

    @pytest.mark.asyncio
    async def test_doctor_cannot_delete_others_order(self):
        doctor_id = uuid.uuid4()
        other_doctor_id = uuid.uuid4()
        order = _make_order(doctor_id=other_doctor_id)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        uc = _make_use_case(order_repo, FakeLabResultRepo())

        with pytest.raises(PermissionError):
            await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")

    @pytest.mark.asyncio
    async def test_admin_can_delete_any_order(self):
        doctor_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        order = _make_order(doctor_id=doctor_id)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        uc = _make_use_case(order_repo, FakeLabResultRepo())

        await uc.execute(order.id, caller_id=admin_id, caller_role="admin")

        assert len(order_repo._store) == 0

    @pytest.mark.asyncio
    async def test_raises_if_order_not_found(self):
        order_repo = FakeLabOrderRepo()
        uc = _make_use_case(order_repo, FakeLabResultRepo())

        with pytest.raises(ValueError, match="not found"):
            await uc.execute(uuid.uuid4(), caller_id=uuid.uuid4(), caller_role="admin")

    @pytest.mark.asyncio
    async def test_cannot_delete_if_has_published_result(self):
        doctor_id = uuid.uuid4()
        order = _make_order(doctor_id=doctor_id)
        result = make_lab_result(order_id=order.id, status=LabResultStatus.PUBLISHED)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        result_repo = FakeLabResultRepo()
        await result_repo.save(result)
        uc = _make_use_case(order_repo, result_repo)

        with pytest.raises(ValueError, match="published"):
            await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")

    # ─── Refund event logic ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_publishes_cancelled_event_for_paid_order_with_fee(self):
        doctor_id = uuid.uuid4()
        order = _make_order(payment_status="PAID", fee=150_000, doctor_id=doctor_id)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        publisher = FakePublisher()
        uc = _make_use_case(order_repo, FakeLabResultRepo(), publisher)

        await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")

        assert len(publisher.calls) == 1
        assert publisher.calls[0]["event_type"] == "lab_order.cancelled"
        assert publisher.calls[0]["payload"]["lab_order_id"] == str(order.id)
        assert publisher.calls[0]["payload"]["amount"] == 150_000

    @pytest.mark.asyncio
    async def test_does_not_publish_event_for_unpaid_order(self):
        doctor_id = uuid.uuid4()
        order = _make_order(payment_status="UNPAID", fee=150_000, doctor_id=doctor_id)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        publisher = FakePublisher()
        uc = _make_use_case(order_repo, FakeLabResultRepo(), publisher)

        await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")

        assert len(publisher.calls) == 0

    @pytest.mark.asyncio
    async def test_does_not_publish_event_for_paid_order_with_zero_fee(self):
        doctor_id = uuid.uuid4()
        order = _make_order(payment_status="PAID", fee=0, doctor_id=doctor_id)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        publisher = FakePublisher()
        uc = _make_use_case(order_repo, FakeLabResultRepo(), publisher)

        await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")

        assert len(publisher.calls) == 0

    @pytest.mark.asyncio
    async def test_event_payload_contains_required_fields(self):
        doctor_id = uuid.uuid4()
        order = _make_order(
            payment_status="PAID",
            fee=200_000,
            doctor_id=doctor_id,
            test_name="Complete Blood Count",
        )
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        publisher = FakePublisher()
        uc = _make_use_case(order_repo, FakeLabResultRepo(), publisher)

        await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")

        payload = publisher.calls[0]["payload"]
        assert "lab_order_id" in payload
        assert "patient_id" in payload
        assert "doctor_id" in payload
        assert "amount" in payload
        assert "test_name" in payload

    @pytest.mark.asyncio
    async def test_still_deletes_order_even_if_publisher_raises(self):
        doctor_id = uuid.uuid4()
        order = _make_order(payment_status="PAID", fee=150_000, doctor_id=doctor_id)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)

        class BrokenPublisher:
            async def publish(self, event_type, payload):
                raise RuntimeError("Publisher down")

        uc = _make_use_case(order_repo, FakeLabResultRepo(), BrokenPublisher())

        # Should not raise — publisher failure is swallowed
        await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")
        assert len(order_repo._store) == 0

    @pytest.mark.asyncio
    async def test_works_without_publisher(self):
        doctor_id = uuid.uuid4()
        order = _make_order(payment_status="PAID", fee=150_000, doctor_id=doctor_id)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        uc = _make_use_case(order_repo, FakeLabResultRepo(), publisher=None)

        # Should complete without error even with no publisher
        await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")
        assert len(order_repo._store) == 0

    @pytest.mark.asyncio
    async def test_cleans_up_pending_results_on_delete(self):
        doctor_id = uuid.uuid4()
        order = _make_order(doctor_id=doctor_id)
        result = make_lab_result(order_id=order.id, status=LabResultStatus.PENDING)
        order_repo = FakeLabOrderRepo()
        await order_repo.save(order)
        result_repo = FakeLabResultRepo()
        await result_repo.save(result)
        uc = _make_use_case(order_repo, result_repo)

        await uc.execute(order.id, caller_id=doctor_id, caller_role="doctor")

        assert len(order_repo._store) == 0
        assert len(result_repo._store) == 0


# ═════════════════════ LabOrder entity tests ════════════════════════════════

class TestLabOrderPaymentStatus:
    def test_default_payment_status_is_unpaid(self):
        order = make_lab_order()
        assert order.payment_status == "UNPAID"

    def test_default_fee_is_zero(self):
        order = make_lab_order()
        assert order.fee == 0

    def test_payment_status_can_be_set_to_paid(self):
        order = make_lab_order(payment_status="PAID")
        assert order.payment_status == "PAID"

    def test_payment_status_can_be_set_to_refund_pending(self):
        order = make_lab_order(payment_status="REFUND_PENDING")
        assert order.payment_status == "REFUND_PENDING"

    def test_fee_is_stored(self):
        order = make_lab_order(fee=250_000)
        assert order.fee == 250_000
