from typing import Any
from uuid import UUID

from Domain.interfaces import IPaymentProvider, PaymentRequest
from Domain.interfaces.payment_repository import IPaymentRepository
from Domain.value_objects.payment_status import PaymentStatus
from infrastructure.config import settings

_PAYABLE_STATUSES = {PaymentStatus.PENDING, PaymentStatus.EXPIRED}


class GeneratePaymentUrlUseCase:
    """
    (Re)generate a VNPay payment URL for an existing payment record.

    Allowed only when the payment is still unpaid (pending or expired).
    Paid, failed, and refunded payments are immutable.
    """

    def __init__(
        self,
        session: Any,
        payment_repo: IPaymentRepository,
        payment_provider: IPaymentProvider,
    ):
        self.session = session
        self.payment_repo = payment_repo
        self.payment_provider = payment_provider

    async def execute(self, appointment_id: UUID, client_ip: str = "127.0.0.1") -> dict:
        payment = await self.payment_repo.get_by_appointment_id(appointment_id)
        if not payment:
            raise ValueError(f"Payment not found for appointment {appointment_id}")

        if payment.status not in _PAYABLE_STATUSES:
            raise PermissionError(
                f"Cannot generate payment URL: payment is already '{payment.status.value}'"
            )

        vnpay_request = PaymentRequest(
            order_id=payment.appointment_id,
            amount=payment.amount,
            order_desc=f"Appointment {payment.appointment_id}",
            return_url=settings.VNPAY_GATEWAY_RETURN_URL,
            client_ip=client_ip,
        )
        payment.payment_url = await self.payment_provider.create_payment_url(vnpay_request)
        # Reset to pending so the expiry window restarts from now
        payment.status = PaymentStatus.PENDING

        await self.payment_repo.save(payment)
        await self.session.commit()

        return {
            "id": str(payment.id),
            "appointment_id": str(payment.appointment_id),
            "status": payment.status.value,
            "amount": payment.amount,
            "currency": payment.currency,
            "payment_url": payment.payment_url,
            "vnpay_txn_ref": payment.vnpay_txn_ref,
        }
