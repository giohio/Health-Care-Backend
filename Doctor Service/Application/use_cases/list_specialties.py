from typing import List

from Application.dtos import SpecialtyDTO
from Domain.interfaces.specialty_repository import ISpecialtyRepository
from healthai_cache import CacheClient

_CACHE_KEY = "doctor:specialties:all"
_CACHE_TTL = 3600  # 60 min — reference data


class ListSpecialtiesUseCase:
    def __init__(self, specialty_repo: ISpecialtyRepository, cache: CacheClient | None = None):
        self.specialty_repo = specialty_repo
        self._cache = cache

    async def execute(self) -> List[SpecialtyDTO]:
        if self._cache:
            cached = await self._cache.get(_CACHE_KEY)
            if cached is not None:
                return [SpecialtyDTO(**s) for s in cached]

        specialties = await self.specialty_repo.list_all()
        result = [SpecialtyDTO.model_validate(s) for s in specialties]

        if self._cache:
            await self._cache.set(_CACHE_KEY, [s.model_dump(mode="json") for s in result], ttl=_CACHE_TTL)

        return result
