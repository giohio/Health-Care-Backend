from datetime import time
from typing import List

from Application.dtos import DoctorDTO
from Domain.interfaces.doctor_repository import IDoctorRepository
from uuid_extension import UUID7


class SearchAvailableDoctorsUseCase:
    def __init__(self, doctor_repo: IDoctorRepository):
        self.doctor_repo = doctor_repo

    async def execute(self, specialty_id: UUID7, day_of_week: int, time_slot: time) -> List[DoctorDTO]:
        doctors = await self.doctor_repo.search_available(specialty_id, day_of_week, time_slot)
        return [DoctorDTO.model_validate(d) for d in doctors]
