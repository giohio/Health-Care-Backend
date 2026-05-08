import uuid
from datetime import date

from Application.dtos import MedicationResponse, UpdateMedicationStatusRequest
from Application.exceptions import MedicationNotFoundError
from Domain.interfaces.medication_repository import IMedicationRepository
from Domain.value_objects.medication_status import MedicationStatus


class UpdateMedicationStatusUseCase:
    """Change the status of a medication (stop or complete)."""

    def __init__(self, medication_repo: IMedicationRepository):
        self.medication_repo = medication_repo

    async def execute(
        self,
        medication_id: uuid.UUID,
        request: UpdateMedicationStatusRequest,
    ) -> MedicationResponse:
        medication = await self.medication_repo.get_by_id(medication_id)
        if medication is None:
            raise MedicationNotFoundError()

        if request.status == MedicationStatus.STOPPED:
            medication.stop()
        elif request.status == MedicationStatus.COMPLETED:
            medication.complete()
        else:
            # Allow explicit set for idempotent retries
            medication.status = request.status

        if request.end_date is not None:
            medication.end_date = request.end_date

        saved = await self.medication_repo.save(medication)
        return MedicationResponse.model_validate(saved, from_attributes=True)
