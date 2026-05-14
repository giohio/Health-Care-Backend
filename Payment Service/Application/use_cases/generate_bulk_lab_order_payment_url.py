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

_PAYABLE_STATUSES = {PaymentStatus.PENDING, PaymentStatus.EXPIRED}


class GenerateBulkLabOrderPaymentUrlUseCase:
    """Create one VNPAY payment URL for several unpaid lab order payments."""

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

    async def execute(
        self,
        patient_id: UUID,
        lab_order_ids: list[UUID],
        client_ip: str = "127.0.0.1",
    ) -> dict:
        unique_ids = list(dict.fromkeys(lab_order_ids))
        if not unique_ids:
            raise ValueError("Select at least one lab order to pay")

        payments = await self.payment_repo.list_by_reference_ids(unique_ids)
        found_ids = {payment.reference_id for payment in payments}
        missing_ids = [str(order_id) for order_id in unique_ids if order_id not in found_ids]
        if missing_ids:
            raise ValueError(f"Payment not found for lab order(s): {', '.join(missing_ids)}")

        for payment in payments:
            if payment.patient_id != patient_id:
                raise PermissionError("You can only pay your own lab orders")
            if payment.status not in _PAYABLE_STATUSES:
                raise PermissionError(
                    f"Lab order {payment.reference_id} is already '{payment.status.value}'"
                )

        if len(payments) == 1:
            payment = payments[0]
            vnpay_request = PaymentRequest(
                order_id=payment.reference_id,
                amount=payment.amount,
                order_desc=f"Lab order {payment.reference_id}",
                return_url=settings.VNPAY_GATEWAY_RETURN_URL,
                client_ip=client_ip,
            )
            payment.payment_url = await self.payment_provider.create_payment_url(vnpay_request)
            payment.status = PaymentStatus.PENDING
            await self.payment_repo.save(payment)
            await self.session.commit()
            return {
                "payment_id": str(payment.id),
                "payment_url": payment.payment_url,
                "lab_order_ids": [str(payment.reference_id)],
                "amount": payment.amount,
            }

        bundle_id = uuid.uuid4()
        total_amount = sum(payment.amount for payment in payments)
        bundle = Payment(
            id=uuid.uuid4(),
            patient_id=patient_id,
            appointment_id=None,
            doctor_id=payments[0].doctor_id,
            amount=total_amount,
            payment_type="LAB_ORDER_BUNDLE",
            reference_id=bundle_id,
            status=PaymentStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        bundle.vnpay_txn_ref = str(bundle_id)
        bundle.payment_url = await self.payment_provider.create_payment_url(
            PaymentRequest(
                order_id=bundle_id,
                amount=total_amount,
                order_desc=f"Lab order payment {len(payments)} tests",
                return_url=settings.VNPAY_GATEWAY_RETURN_URL,
                client_ip=client_ip,
            )
        )

        await self.payment_repo.save(bundle)
        await self.payment_repo.append_transaction(
            payment_id=bundle.id,
            appointment_id=None,
            transaction_type=PaymentTransactionType.PAYMENT_CREATED,
            amount=bundle.amount,
            currency=bundle.currency,
            provider_ref=bundle.vnpay_txn_ref,
            metadata={
                "source": "bulk_lab_order_payment",
                "lab_order_ids": [str(payment.reference_id) for payment in payments],
                "child_payment_ids": [str(payment.id) for payment in payments],
            },
        )
        await self.session.commit()

        return {
            "payment_id": str(bundle.id),
            "payment_url": bundle.payment_url,
            "lab_order_ids": [str(payment.reference_id) for payment in payments],
            "amount": total_amount,
        }
