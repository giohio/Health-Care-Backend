from datetime import date

from healthai_cache import CacheClient
from uuid_extension import UUID7


class AddDayOffUseCase:
    def __init__(self, day_off_repo, cache: CacheClient | None = None):
        self.day_off_repo = day_off_repo
        self._cache = cache

    async def execute(self, doctor_id: UUID7, off_date: date, reason: str = None):
        result = await self.day_off_repo.create(doctor_id, off_date, reason)
        if self._cache:
            year_month = off_date.strftime("%Y-%m")
            await self._cache.delete(
                f"doctor:dayoffs:{doctor_id}:{year_month}",
                f"doctor:enhanced_schedule:{doctor_id}:{off_date}",
            )
        return result


class RemoveDayOffUseCase:
    def __init__(self, day_off_repo, cache: CacheClient | None = None):
        self.day_off_repo = day_off_repo
        self._cache = cache

    async def execute(self, doctor_id: UUID7, off_date: date):
        result = await self.day_off_repo.delete(doctor_id, off_date)
        if self._cache:
            year_month = off_date.strftime("%Y-%m")
            await self._cache.delete(
                f"doctor:dayoffs:{doctor_id}:{year_month}",
                f"doctor:enhanced_schedule:{doctor_id}:{off_date}",
            )
        return result
