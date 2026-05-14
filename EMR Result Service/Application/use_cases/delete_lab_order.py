from uuid import UUID

from Domain.interfaces.lab_order_repository import ILabOrderRepository
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus


class DeleteLabOrderUseCase:
    """
    Permanently delete a lab order.

    Business rules:
    - Doctors can only delete their OWN orders.
    - Admins can delete any order.
    - Orders with an associated published/verified lab result cannot be deleted.
    - Deleting an order will also clean up any associated AI drafts or pending results.
    - If the order has a fee, publish lab_order.cancelled so Payment Service can
      remove pending payments or mark paid payments for refund.
    """

    def __init__(
        self,
        order_repo: ILabOrderRepository,
        result_repo: ILabResultRepository,
        event_publisher=None,
    ):
        self._order_repo = order_repo
        self._result_repo = result_repo
        self._publisher = event_publisher

    async def execute(
        self,
        order_id: UUID,
        caller_id: UUID,
        caller_role: str,
    ) -> None:
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise ValueError(f"Lab order {order_id} not found.")

        if caller_role == "doctor" and order.doctor_id != caller_id:
            raise PermissionError("You can only delete your own lab orders.")

        # Check for associated results
        results = await self._result_repo.list_by_order_ids([order_id])
        
        # Rule: Cannot delete if any result is PUBLISHED
        if any(r.status == LabResultStatus.PUBLISHED for r in results):
            raise ValueError("Cannot delete an order that has already been published.")

        # Notify Payment Service so pending lab payments disappear from patient
        # history, while paid orders can move into the refund workflow.
        if order.fee > 0 and self._publisher:
            try:
                await self._publisher.publish(
                    event_type="lab_order.cancelled",
                    payload={
                        "lab_order_id": str(order.id),
                        "patient_id": str(order.patient_id),
                        "doctor_id": str(order.doctor_id),
                        "amount": order.fee,
                        "test_name": order.test_name,
                        "payment_status": order.payment_status,
                    },
                )
            except Exception:
                import logging
                logger = logging.getLogger(__name__)
                logger.exception("Failed to publish lab_order.cancelled for %s", order_id)

        # Cleanup: Delete all associated results that are not published
        for r in results:
            await self._result_repo.delete(r.id)

        await self._order_repo.delete(order_id)
