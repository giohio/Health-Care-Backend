"""Consumer for lab order deletion events from EMR Service.

Pending/unpaid lab payments are deleted from patient history. Paid lab payments
move to REFUND_PENDING so admin can manually process the refund.
"""
import logging
from uuid import UUID

from healthai_events.consumer import BaseConsumer

logger = logging.getLogger(__name__)


class LabOrderCancelledConsumer(BaseConsumer):
    """Listens for lab_order.cancelled events on the lab_order_events exchange."""

    QUEUE = "payment.lab_order_cancelled"
    EXCHANGE = "lab_order_events"
    ROUTING_KEY = "lab_order.cancelled"

    def __init__(self, connection, cache, session_factory, payment_repo_factory, event_publisher):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._payment_repo_factory = payment_repo_factory
        self._event_publisher = event_publisher

    async def handle(self, payload: dict) -> None:
        lab_order_id_raw = payload.get("lab_order_id")
        if not lab_order_id_raw:
            logger.warning("lab_order.cancelled event missing lab_order_id: %s", payload)
            return

        try:
            lab_order_id = UUID(str(lab_order_id_raw))
        except (ValueError, AttributeError):
            logger.warning("lab_order.cancelled invalid lab_order_id: %s", lab_order_id_raw)
            return

        if not self._session_factory or not self._payment_repo_factory:
            logger.warning("lab_order.cancelled: session_factory or payment_repo_factory not configured")
            return

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = self._payment_repo_factory(session)
                    payment = await repo.get_by_reference_id(lab_order_id)
                    if not payment:
                        logger.warning("lab_order.cancelled: payment not found for lab_order %s", lab_order_id)
                        return

                    if payment.status.value != "paid":
                        await repo.delete_by_reference_id(lab_order_id)
                        logger.info("Deleted unpaid payment for cancelled lab_order %s", lab_order_id)
                        return

                    payment.mark_as_refund_pending()
                    await repo.save(payment)

                    # Publish event for audit trail
                    if self._event_publisher:
                        try:
                            await self._event_publisher.publish(
                                exchange="payment_events",
                                routing_key="payment.refund_pending",
                                payload={
                                    "payment_id": str(payment.id),
                                    "lab_order_id": str(lab_order_id),
                                    "patient_id": str(payment.patient_id),
                                    "amount": payment.amount,
                                },
                            )
                        except Exception:
                            logger.exception("Failed to publish payment.refund_pending event")

                    logger.info(
                        "Payment %s marked REFUND_PENDING (lab_order=%s, amount=%s)",
                        payment.id,
                        lab_order_id,
                        payment.amount,
                    )

        except Exception:
            logger.exception("Failed to process lab_order.cancelled for lab_order %s", lab_order_id)
