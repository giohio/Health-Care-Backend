from Domain.interfaces.rating_repository import IRatingRepository
from healthai_cache import CacheClient
from uuid_extension import UUID7

_CACHE_TTL = 300  # 5 min


class ListRatingsUseCase:
    def __init__(self, rating_repo: IRatingRepository, cache: CacheClient | None = None):
        self.rating_repo = rating_repo
        self._cache = cache

    async def execute(self, doctor_id: UUID7, page: int = 1, limit: int = 20):
        cache_key = f"doctor:ratings:{doctor_id}:page{page}:limit{limit}"
        if self._cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached

        offset = (page - 1) * limit
        ratings = await self.rating_repo.list_by_doctor(doctor_id, limit, offset)

        if self._cache and ratings is not None:
            import json
            serializable = json.loads(json.dumps(
                [r.__dict__ if hasattr(r, "__dict__") else r for r in ratings], default=str
            ))
            await self._cache.set(cache_key, serializable, ttl=_CACHE_TTL)

        return ratings
