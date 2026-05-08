import uuid
from typing import List, Optional

from Application.dtos import DiagnosisResponse, PatientSummaryResponse, MedicationResponse
from Domain.interfaces.clinical_note_repository import IClinicalNoteRepository
from Domain.interfaces.diagnosis_repository import IDiagnosisRepository
from Domain.interfaces.medication_repository import IMedicationRepository
from Domain.interfaces.patient_service_client import IPatientServiceClient
from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.medication_status import MedicationStatus


class GetPatientSummaryUseCase:
    """Aggregate a complete clinical snapshot for a patient.

    Calls patient_service to fetch allergies and latest vitals, then joins
    with local diagnoses and medications.  All external failures are handled
    gracefully — the summary still returns with empty/null fields.
    """

    def __init__(
        self,
        diagnosis_repo: IDiagnosisRepository,
        medication_repo: IMedicationRepository,
        patient_client: IPatientServiceClient,
    ):
        self.diagnosis_repo = diagnosis_repo
        self.medication_repo = medication_repo
        self.patient_client = patient_client

    async def execute(self, patient_id: uuid.UUID) -> PatientSummaryResponse:
        # Do DB queries sequentially: one AsyncSession cannot run concurrent operations.
        diagnoses = await self.diagnosis_repo.list_by_patient(patient_id)
        medications = await self.medication_repo.list_by_patient(patient_id, status=MedicationStatus.ACTIVE)

        # External HTTP calls can run concurrently.
        import asyncio

        allergies, vitals = await asyncio.gather(
            self.patient_client.get_allergies(patient_id),
            self.patient_client.get_latest_vitals(patient_id),
        )

        return PatientSummaryResponse(
            patient_id=patient_id,
            diagnoses=[DiagnosisResponse.model_validate(d, from_attributes=True) for d in diagnoses],
            medications=[MedicationResponse.model_validate(m, from_attributes=True) for m in medications],
            allergies=allergies,
            vitals_latest=vitals,
        )
