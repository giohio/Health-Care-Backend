from Application.dtos import SpecialtyDTO
from Domain.entities.specialty import Specialty
from Domain.exceptions.domain_exceptions import SpecialtyAlreadyExistsException
from Domain.interfaces.specialty_repository import ISpecialtyRepository
from healthai_cache import CacheClient
from uuid_extension import UUID7

_CACHE_KEY = "doctor:specialties:all"


class SaveSpecialtyUseCase:
    def __init__(self, specialty_repo: ISpecialtyRepository, cache: CacheClient | None = None):
        self.specialty_repo = specialty_repo
        self._cache = cache

    async def execute(self, dto: SpecialtyDTO) -> SpecialtyDTO:
        # If ID is provided, it's an update, otherwise create new
        specialty_id = dto.id or UUID7()

        # Check if name already exists for a different ID
        existing = await self.specialty_repo.get_by_name(dto.name)
        if existing and existing.id != specialty_id:
            raise SpecialtyAlreadyExistsException(dto.name)

        specialty = Specialty(id=specialty_id, name=dto.name, description=dto.description)

        saved = await self.specialty_repo.save(specialty)

        if self._cache:
            await self._cache.delete(_CACHE_KEY)

        return SpecialtyDTO(
            id=str(saved.id),
            name=saved.name,
            description=saved.description,
        )
