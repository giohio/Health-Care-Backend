import uuid

from Application.dtos import DiagnosisResponse, UpdateDiagnosisRequest
from Application.exceptions import DiagnosisNotFoundError
from Domain.interfaces.diagnosis_repository import IDiagnosisRepository


class UpdateDiagnosisUseCase:
    """Update mutable fields of a diagnosis (status, detail, severity, etc.)."""

    def __init__(self, diagnosis_repo: IDiagnosisRepository):
        self.diagnosis_repo = diagnosis_repo

    async def execute(
        self,
        diagnosis_id: uuid.UUID,
        request: UpdateDiagnosisRequest,
    ) -> DiagnosisResponse:
        diagnosis = await self.diagnosis_repo.get_by_id(diagnosis_id)
        if diagnosis is None:
            raise DiagnosisNotFoundError()

        if request.status is not None:
            diagnosis.status = request.status
        if request.resolved_at is not None:
            diagnosis.resolved_at = request.resolved_at
        if request.diagnosis_detail is not None:
            diagnosis.diagnosis_detail = request.diagnosis_detail
        if request.severity is not None:
            diagnosis.severity = request.severity
        if request.icd10_code is not None:
            diagnosis.icd10_code = request.icd10_code

        saved = await self.diagnosis_repo.save(diagnosis)
        return DiagnosisResponse.model_validate(saved, from_attributes=True)
