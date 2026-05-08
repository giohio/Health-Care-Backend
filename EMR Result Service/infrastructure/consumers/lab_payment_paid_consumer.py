"""Consumer that listens for ``lab_payment.paid`` events published by the
Payment Service after a patient completes payment for a lab order.

When this event is received the consumer updates the lab order payment status
to PAID in the database, allowing the doctor to proceed with uploading the lab result.
"""
import logging
from uuid import UUID

from healthai_events.consumer import BaseConsumer

logger = logging.getLogger(__name__)


class LabPaymentPaidConsumer(BaseConsumer):
    """Listens for ``lab_payment.paid`` events on the ``payment_events`` exchange."""

    QUEUE = "emr.lab_payment_paid"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "lab_payment.paid"

    def __init__(self, connection, cache, session_factory, order_repo_factory):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._order_repo_factory = order_repo_factory

    async def handle(self, payload: dict) -> None:
        lab_order_id_raw = payload.get("lab_order_id")
        if not lab_order_id_raw:
            logger.warning("lab_payment.paid event missing lab_order_id: %s", payload)
            return

        try:
            lab_order_id = UUID(str(lab_order_id_raw))
        except (ValueError, AttributeError):
            logger.warning("lab_payment.paid invalid lab_order_id: %s", lab_order_id_raw)
            return

        # Update DB: mark order as PAID
        if not self._session_factory or not self._order_repo_factory:
            logger.warning(
                "lab_payment.paid: session_factory or order_repo_factory not configured (lab_order_id=%s)",
                lab_order_id,
            )
            return

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = self._order_repo_factory(session)
                    order = await repo.get_by_id(lab_order_id)
                    if order is None:
                        logger.warning("lab_payment.paid: order %s not found", lab_order_id)
                        return
                    order.payment_status = "PAID"
                    await repo.save(order)
                    logger.info("Lab order %s marked as PAID", lab_order_id)
        except Exception as e:
            logger.exception("Failed to update payment status for lab_order %s: %s", lab_order_id, e)
