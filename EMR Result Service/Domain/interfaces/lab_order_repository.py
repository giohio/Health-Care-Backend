from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from Domain.entities.lab_order import LabOrder
from Domain.value_objects.order_priority import OrderPriority


class ILabOrderRepository(ABC):
    @abstractmethod
    async def save(self, order: LabOrder) -> LabOrder:
        """Persist a new lab order."""

    @abstractmethod
    async def get_by_id(self, order_id: UUID) -> Optional[LabOrder]:
        """Return a lab order by id, or None."""

    @abstractmethod
    async def list(
        self,
        patient_id: Optional[UUID] = None,
        doctor_id: Optional[UUID] = None,
    ) -> List[LabOrder]:
        """List orders with optional patient/doctor filter, newest first."""

    @abstractmethod
    async def list_by_appointment_id(self, appointment_id: UUID) -> List[LabOrder]:
        """List all orders for a given appointment, oldest first."""

    @abstractmethod
    async def delete(self, order_id: UUID) -> None:
        """Permanently delete a lab order by id. Raises ValueError if not found."""
