"""Use case: Admin marks a refund_pending payment as refunded."""
import logging
from uuid import UUID

from Domain.value_objects.payment_status import PaymentStatus

logger = logging.getLogger(__name__)


class MarkPaymentRefundedUseCase:
    """Admin manually confirms that a refund has been processed."""

    def __init__(self, session, payment_repo, event_publisher=None):
        self.session = session
        self.payment_repo = payment_repo
        self.event_publisher = event_publisher

    async def execute(self, payment_id: UUID) -> dict:
        """
        Mark a REFUND_PENDING payment as REFUNDED.

        Args:
            payment_id: UUID of the payment to mark as refunded.

        Returns:
            Dictionary with status and payment_id.

        Raises:
            ValueError: If payment not found.
            PermissionError: If payment is not in REFUND_PENDING status.
        """
        payment = await self.payment_repo.get_by_id(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status != PaymentStatus.REFUND_PENDING:
            raise PermissionError(
                f"Payment is {payment.status.value}, not {PaymentStatus.REFUND_PENDING.value}"
            )

        # Mark as refunded
        payment.mark_as_refunded()
        await self.payment_repo.save(payment)

        # Publish event for audit trail
        if self.event_publisher:
            try:
                await self.event_publisher.publish(
                    exchange="payment_events",
                    routing_key="payment.refunded",
                    payload={
                        "payment_id": str(payment.id),
                        "patient_id": str(payment.patient_id),
                        "payment_type": payment.payment_type,
                        "reference_id": str(payment.reference_id) if payment.reference_id else None,
                        "amount": payment.amount,
                    },
                )
            except Exception:
                logger.exception("Failed to publish payment.refunded event for payment %s", payment_id)

        await self.session.commit()

        logger.info("Payment %s marked as REFUNDED by admin", payment_id)

        return {"status": "refunded", "payment_id": str(payment_id)}
