from Application.dtos import SpecialtyDTO
from Domain.entities.specialty import Specialty
from Domain.exceptions.domain_exceptions import SpecialtyAlreadyExistsException
from Domain.interfaces.specialty_repository import ISpecialtyRepository
from uuid_extension import UUID7


class SaveSpecialtyUseCase:
    def __init__(self, specialty_repo: ISpecialtyRepository):
        self.specialty_repo = specialty_repo

    async def execute(self, dto: SpecialtyDTO) -> SpecialtyDTO:
        # If ID is provided, it's an update, otherwise create new
        specialty_id = dto.id or UUID7()

        # Check if name already exists for a different ID
        existing = await self.specialty_repo.get_by_name(dto.name)
        if existing and existing.id != specialty_id:
            raise SpecialtyAlreadyExistsException(dto.name)

        specialty = Specialty(id=specialty_id, name=dto.name, description=dto.description)

        saved = await self.specialty_repo.save(specialty)
        return SpecialtyDTO.model_validate(saved)
