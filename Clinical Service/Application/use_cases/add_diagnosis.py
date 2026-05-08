import uuid
from datetime import datetime, timezone

from Application.dtos import CreateDiagnosisRequest, DiagnosisResponse
from Domain.entities.diagnosis import Diagnosis
from Domain.interfaces.diagnosis_repository import IDiagnosisRepository


class AddDiagnosisUseCase:
    """Doctor adds a diagnosis to a patient's clinical record."""

    def __init__(self, diagnosis_repo: IDiagnosisRepository):
        self.diagnosis_repo = diagnosis_repo

    async def execute(self, request: CreateDiagnosisRequest) -> DiagnosisResponse:
        diagnosis = Diagnosis(
            id=uuid.uuid4(),
            patient_id=request.patient_id,
            doctor_id=request.doctor_id,
            appointment_id=request.appointment_id,
            icd10_code=request.icd10_code,
            diagnosis_name=request.diagnosis_name,
            diagnosis_detail=request.diagnosis_detail,
            severity=request.severity,
            status=request.status,
            diagnosed_at=request.diagnosed_at,
            source=request.source,
        )
        saved = await self.diagnosis_repo.save(diagnosis)
        return DiagnosisResponse.model_validate(saved, from_attributes=True)
