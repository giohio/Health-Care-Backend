from typing import List
from Domain.interfaces.specialty_repository import ISpecialtyRepository
from Application.dtos import SpecialtyDTO

class ListSpecialtiesUseCase:
    def __init__(self, specialty_repo: ISpecialtyRepository):
        self.specialty_repo = specialty_repo

    async def execute(self) -> List[SpecialtyDTO]:
        specialties = await self.specialty_repo.list_all()
        return [SpecialtyDTO.model_validate(s) for s in specialties]
