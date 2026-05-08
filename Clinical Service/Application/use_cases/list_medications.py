import uuid
from typing import List, Optional

from Application.dtos import MedicationResponse
from Domain.interfaces.medication_repository import IMedicationRepository
from Domain.value_objects.medication_status import MedicationStatus


class ListMedicationsUseCase:
    """List all medications for a patient, with optional status filter."""

    def __init__(self, medication_repo: IMedicationRepository):
        self.medication_repo = medication_repo

    async def execute(
        self,
        patient_id: uuid.UUID,
        status: Optional[MedicationStatus] = None,
    ) -> List[MedicationResponse]:
        medications = await self.medication_repo.list_by_patient(patient_id, status=status)
        return [MedicationResponse.model_validate(m, from_attributes=True) for m in medications]
