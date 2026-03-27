from healthai_cache import CacheClient
from uuid_extension import UUID7


class SetAvailabilityUseCase:
    def __init__(self, availability_repo, cache: CacheClient | None = None):
        self.availability_repo = availability_repo
        self._cache = cache

    async def execute(
        self,
        doctor_id: UUID7,
        day_of_week: int,
        start_time,
        end_time,
        break_start=None,
        break_end=None,
        max_patients=20,
    ):
        result = await self.availability_repo.upsert(
            doctor_id, day_of_week, start_time, end_time, break_start, break_end, max_patients
        )
        if hasattr(self.availability_repo, "session"):
            await self.availability_repo.session.commit()

        if self._cache:
            await self._cache.delete(f"doctor:availability:{doctor_id}")
            await self._cache.delete_pattern(f"doctor:enhanced_schedule:{doctor_id}:*")

        return result
