from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from Domain.entities.lab_result import LabResult
from Domain.value_objects.lab_result_status import LabResultStatus


class ILabResultRepository(ABC):
    @abstractmethod
    async def save(self, result: LabResult) -> LabResult:
        """Persist or update a lab result."""

    @abstractmethod
    async def get_by_id(self, result_id: UUID) -> Optional[LabResult]:
        """Return a lab result by id, or None."""

    @abstractmethod
    async def list(
        self,
        patient_id: Optional[UUID] = None,
        doctor_id: Optional[UUID] = None,
        status: Optional[LabResultStatus] = None,
        reviewer_doctor_id: Optional[UUID] = None,
        required_specialty: Optional[str] = None,
        open_claim: Optional[bool] = None,
    ) -> List[LabResult]:
        """List results with optional filters, newest first.

        open_claim=True  → reviewer_doctor_id IS NULL (unclaimed specialty results)
        """

    @abstractmethod
    async def list_by_order_ids(self, order_ids: List[UUID]) -> List[LabResult]:
        """Return all results whose order_id is in order_ids."""

    @abstractmethod
    async def delete(self, result_id: UUID) -> None:
        """Permanently delete a lab result."""
