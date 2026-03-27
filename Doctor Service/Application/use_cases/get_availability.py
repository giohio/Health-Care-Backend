from healthai_cache import CacheClient
from uuid_extension import UUID7

_CACHE_TTL = 600  # 10 min


class GetAvailabilityUseCase:
    def __init__(self, availability_repo, cache: CacheClient | None = None):
        self.availability_repo = availability_repo
        self._cache = cache

    async def execute(self, doctor_id: UUID7):
        cache_key = f"doctor:availability:{doctor_id}"
        if self._cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached

        result = await self.availability_repo.get_by_doctor(doctor_id)

        if self._cache and result is not None:
            import json
            serializable = json.loads(json.dumps(result, default=str))
            await self._cache.set(cache_key, serializable, ttl=_CACHE_TTL)

        return result
