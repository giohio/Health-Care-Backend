import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from Domain.entities.payment import Payment
from Domain.interfaces import IEventPublisher, IPaymentProvider, PaymentRequest
from Domain.interfaces.payment_repository import IPaymentRepository
from Domain.value_objects.payment_status import PaymentStatus
from Domain.value_objects.payment_transaction_type import PaymentTransactionType
from infrastructure.config import settings


class CreateLabOrderPaymentUseCase:
    """Create a VNPAY payment for a lab order.

    Triggered by a ``lab_order.payment_required`` event from the EMR Result Service.
    Creates a Payment with ``payment_type='LAB_ORDER'``, ``reference_id=lab_order_id``,
    and ``appointment_id=None``.  The vnpay_txn_ref uses the ``LAB_{lab_order_id}``
    format so IPN callbacks can distinguish lab payments from appointment payments.
    """

    def __init__(
        self,
        session: Any,
        payment_repo: IPaymentRepository,
        payment_provider: IPaymentProvider,
        event_publisher: IEventPublisher,
    ):
        self.session = session
        self.payment_repo = payment_repo
        self.payment_provider = payment_provider
        self.event_publisher = event_publisher

    async def execute(self, payload: dict) -> Payment:
        """Create payment and generate VNPAY payment URL.

        Args:
            payload: {lab_order_id, patient_id, doctor_id, amount, test_name, ...}
        """
        lab_order_id = UUID(str(payload["lab_order_id"]))
        patient_id = UUID(str(payload["patient_id"]))
        doctor_id = UUID(str(payload["doctor_id"]))
        amount = int(payload.get("amount", 200000))
        test_name = payload.get("test_name", "Lab test")

        payment = Payment(
            id=uuid.uuid4(),
            patient_id=patient_id,
            appointment_id=None,
            doctor_id=doctor_id,
            amount=amount,
            payment_type="LAB_ORDER",
            reference_id=lab_order_id,
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        # LAB_ prefix distinguishes from appointment payments (plain UUID format)
        payment.vnpay_txn_ref = f"LAB_{lab_order_id}"

        vnpay_request = PaymentRequest(
            order_id=lab_order_id,
            amount=amount,
            order_desc=f"Lab test: {test_name}",
            return_url=settings.VNPAY_GATEWAY_RETURN_URL,
            client_ip="127.0.0.1",
        )
        payment.payment_url = await self.payment_provider.create_payment_url(vnpay_request)

        await self.payment_repo.save(payment)
        await self.payment_repo.append_transaction(
            payment_id=payment.id,
            appointment_id=None,
            transaction_type=PaymentTransactionType.PAYMENT_CREATED,
            amount=payment.amount,
            currency=payment.currency,
            provider_ref=payment.vnpay_txn_ref,
            metadata={"source_event": "lab_order.payment_required", "lab_order_id": str(lab_order_id)},
        )

        await self.event_publisher.publish(
            session=self.session,
            aggregate_id=payment.id,
            aggregate_type="payment_events",
            event_type="payment.created",
            payload={
                "payment_id": str(payment.id),
                "patient_id": str(payment.patient_id),
                "doctor_id": str(payment.doctor_id),
                "lab_order_id": str(lab_order_id),
                "payment_type": payment.payment_type,
                "amount": payment.amount,
                "status": payment.status.value,
                "payment_url": payment.payment_url,
                "vnpay_txn_ref": payment.vnpay_txn_ref,
            },
        )

        # Schedule expiry check (15 minutes)
        from datetime import timedelta
        expiry_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        await self.event_publisher.publish(
            session=self.session,
            aggregate_id=payment.id,
            aggregate_type="payment_events",
            event_type="payment.check_expiry",
            payload={
                "payment_id": str(payment.id),
                "lab_order_id": str(lab_order_id),
                "check_at": expiry_at,
            },
        )

        return payment
