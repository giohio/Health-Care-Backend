from healthai_cache import CacheClient
from uuid_extension import UUID7

_CACHE_TTL = 600  # 10 min


class AddServiceOfferingUseCase:
    def __init__(self, service_repo, cache: CacheClient | None = None):
        self.service_repo = service_repo
        self._cache = cache

    async def execute(
        self, doctor_id: UUID7, service_name: str, duration_minutes: int, fee: float, description: str = None
    ):
        result = await self.service_repo.create(doctor_id, service_name, duration_minutes, fee, description)
        if self._cache:
            await self._cache.delete(f"doctor:services:{doctor_id}")
            await self._cache.delete_pattern(f"doctor:enhanced_schedule:{doctor_id}:*")
        return result


class UpdateServiceOfferingUseCase:
    def __init__(self, service_repo, cache: CacheClient | None = None):
        self.service_repo = service_repo
        self._cache = cache

    async def execute(self, service_id: UUID7, **kwargs):
        result = await self.service_repo.update(service_id, **kwargs)
        if self._cache and hasattr(result, "doctor_id"):
            await self._cache.delete(f"doctor:services:{result.doctor_id}")
            await self._cache.delete_pattern(f"doctor:enhanced_schedule:{result.doctor_id}:*")
        return result


class ListServiceOfferingsUseCase:
    def __init__(self, service_repo, cache: CacheClient | None = None):
        self.service_repo = service_repo
        self._cache = cache

    async def execute(self, doctor_id: UUID7):
        cache_key = f"doctor:services:{doctor_id}"
        if self._cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached

        result = await self.service_repo.list_by_doctor(doctor_id)

        if self._cache and result is not None:
            import json
            serializable = json.loads(json.dumps(
                [r.__dict__ if hasattr(r, "__dict__") else r for r in result], default=str
            ))
            await self._cache.set(cache_key, serializable, ttl=_CACHE_TTL)

        return result


class DeactivateServiceOfferingUseCase:
    def __init__(self, service_repo, cache: CacheClient | None = None):
        self.service_repo = service_repo
        self._cache = cache

    async def execute(self, service_id: UUID7):
        result = await self.service_repo.deactivate(service_id)
        if self._cache and hasattr(result, "doctor_id"):
            await self._cache.delete(f"doctor:services:{result.doctor_id}")
            await self._cache.delete_pattern(f"doctor:enhanced_schedule:{result.doctor_id}:*")
        return result
