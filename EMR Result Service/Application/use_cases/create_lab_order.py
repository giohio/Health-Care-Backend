import logging
import uuid
from typing import Optional

from Application.dtos import CreateLabOrderRequest, LabOrderResponse
from Application.exceptions import DuplicateLabOrderError
from Domain.entities.lab_order import LabOrder
from Domain.interfaces.lab_order_repository import ILabOrderRepository

logger = logging.getLogger(__name__)


class CreateLabOrderUseCase:
    """Doctor creates a new lab order for a patient."""

    def __init__(self, order_repo: ILabOrderRepository, event_publisher=None):
        self.order_repo = order_repo
        self._publisher = event_publisher

    async def execute(self, request: CreateLabOrderRequest) -> LabOrderResponse:
        if request.appointment_id:
            existing_orders = await self.order_repo.list_by_appointment_id(request.appointment_id)
            requested_name = self._normalize_test_name(request.test_name)
            if any(self._normalize_test_name(order.test_name) == requested_name for order in existing_orders):
                raise DuplicateLabOrderError(request.test_name)

        order = LabOrder(
            id=uuid.uuid4(),
            patient_id=request.patient_id,
            doctor_id=request.doctor_id,
            appointment_id=request.appointment_id,
            test_name=request.test_name,
            test_type=request.test_type,
            department=request.department,
            instructions=request.instructions,
            priority=request.priority,
            fee=request.fee,
        )
        saved = await self.order_repo.save(order)

        # Publish payment_required event if a fee is set
        if saved.fee > 0 and self._publisher is not None:
            try:
                await self._publisher.publish(
                    event_type="lab_order.payment_required",
                    payload={
                        "lab_order_id": str(saved.id),
                        "patient_id": str(saved.patient_id),
                        "doctor_id": str(saved.doctor_id),
                        "amount": saved.fee,
                        "test_name": saved.test_name,
                        "appointment_id": str(saved.appointment_id) if saved.appointment_id else None,
                    },
                )
            except Exception:
                logger.exception("Failed to publish lab_order.payment_required for order %s", saved.id)

        return LabOrderResponse.model_validate(saved, from_attributes=True)

    @staticmethod
    def _normalize_test_name(value: str) -> str:
        return " ".join(str(value or "").strip().lower().split())
