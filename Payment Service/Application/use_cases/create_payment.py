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


class CreatePaymentFromEventUseCase:
    """Create payment record from appointment_events → appointment.payment_required"""

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
        """
        Create payment and generate VNPAY payment URL

        Args:
            payload: {appointment_id, patient_id, doctor_id, appointment_date, amount, ...}
        """
        appointment_id = UUID(str(payload["appointment_id"]))
        patient_id = UUID(str(payload["patient_id"]))
        doctor_id = UUID(str(payload["doctor_id"]))
        amount = int(payload.get("amount", 500000))

        # Create payment entity
        payment = Payment(
            id=uuid.uuid4(),
            appointment_id=appointment_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            amount=amount,
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        # Generate VNPAY transaction reference — must match vnp_TxnRef sent to VNPay
        payment.vnpay_txn_ref = str(appointment_id)

        # Generate payment URL via VNPAY
        vnpay_request = PaymentRequest(
            order_id=appointment_id,
            amount=amount,
            order_desc=f"Appointment {appointment_id}",
            return_url=settings.VNPAY_GATEWAY_RETURN_URL,
            client_ip="127.0.0.1",
        )
        payment.payment_url = await self.payment_provider.create_payment_url(vnpay_request)

        # Save payment record
        await self.payment_repo.save(payment)
        await self.payment_repo.append_transaction(
            payment_id=payment.id,
            appointment_id=payment.appointment_id,
            transaction_type=PaymentTransactionType.PAYMENT_CREATED,
            amount=payment.amount,
            currency=payment.currency,
            provider_ref=payment.vnpay_txn_ref,
            metadata={
                "source_event": "appointment.payment_required",
            },
        )

        # Publish payment.created event
        await self.event_publisher.publish(
            session=self.session,
            aggregate_id=payment.id,
            aggregate_type="payment_events",
            event_type="payment.created",
            payload={
                "payment_id": str(payment.id),
                "appointment_id": str(payment.appointment_id),
                "patient_id": str(payment.patient_id),
                "doctor_id": str(payment.doctor_id),
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
                "appointment_id": str(payment.appointment_id),
                "check_at": expiry_at,
            },
        )

        return payment
