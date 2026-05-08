import uuid
from typing import List

from Application.dtos import VaccinationResponse
from Domain.interfaces.vaccination_repository import IVaccinationRepository


class ListVaccinationsUseCase:
    def __init__(self, vaccination_repo: IVaccinationRepository):
        self.vaccination_repo = vaccination_repo

    async def execute(self, patient_id: uuid.UUID) -> List[VaccinationResponse]:
        vaccinations = await self.vaccination_repo.list_by_patient(patient_id)
        return [VaccinationResponse.model_validate(v, from_attributes=True) for v in vaccinations]