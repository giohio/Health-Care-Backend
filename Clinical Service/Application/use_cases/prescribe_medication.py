import uuid

from Application.dtos import CreateMedicationRequest, MedicationResponse
from Domain.entities.medication import Medication
from Domain.interfaces.medication_repository import IMedicationRepository


class PrescribeMedicationUseCase:
    """Doctor prescribes a new medication for a patient."""

    def __init__(self, medication_repo: IMedicationRepository):
        self.medication_repo = medication_repo

    async def execute(self, request: CreateMedicationRequest) -> MedicationResponse:
        medication = Medication(
            id=uuid.uuid4(),
            patient_id=request.patient_id,
            doctor_id=request.doctor_id,
            appointment_id=request.appointment_id,
            drug_name=request.drug_name,
            dosage=request.dosage,
            frequency=request.frequency,
            route=request.route,
            start_date=request.start_date,
            end_date=request.end_date,
            notes=request.notes,
        )
        saved = await self.medication_repo.save(medication)
        return MedicationResponse.model_validate(saved, from_attributes=True)
