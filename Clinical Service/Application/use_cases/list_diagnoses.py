import uuid
from typing import List, Optional

from Application.dtos import DiagnosisResponse
from Domain.interfaces.diagnosis_repository import IDiagnosisRepository
from Domain.value_objects.diagnosis_status import DiagnosisStatus


class ListDiagnosesUseCase:
    """List all diagnoses for a patient, with optional status filter."""

    def __init__(self, diagnosis_repo: IDiagnosisRepository):
        self.diagnosis_repo = diagnosis_repo

    async def execute(
        self,
        patient_id: uuid.UUID,
        status: Optional[DiagnosisStatus] = None,
    ) -> List[DiagnosisResponse]:
        diagnoses = await self.diagnosis_repo.list_by_patient(patient_id, status=status)
        return [DiagnosisResponse.model_validate(d, from_attributes=True) for d in diagnoses]
