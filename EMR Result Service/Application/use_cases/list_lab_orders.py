import uuid
from typing import List, Optional

from Application.dtos import LabOrderResponse
from Domain.interfaces.lab_order_repository import ILabOrderRepository


class ListLabOrdersUseCase:
    """List lab orders, filtered by patient and/or doctor."""

    def __init__(self, order_repo: ILabOrderRepository):
        self.order_repo = order_repo

    async def execute(
        self,
        patient_id: Optional[uuid.UUID] = None,
        doctor_id: Optional[uuid.UUID] = None,
    ) -> List[LabOrderResponse]:
        orders = await self.order_repo.list(patient_id=patient_id, doctor_id=doctor_id)
        return [LabOrderResponse.model_validate(o, from_attributes=True) for o in orders]
