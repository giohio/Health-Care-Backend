from datetime import date

from healthai_cache import CacheClient
from uuid_extension import UUID7

_CACHE_TTL = 120  # 2 min — computed availability


class GetEnhancedScheduleUseCase:
    def __init__(self, availability_repo, day_off_repo, service_offering_repo, cache: CacheClient | None = None):
        self.availability_repo = availability_repo
        self.day_off_repo = day_off_repo
        self.service_offering_repo = service_offering_repo
        self._cache = cache

    async def execute(self, doctor_id: UUID7, target_date: date):
        cache_key = f"doctor:enhanced_schedule:{doctor_id}:{target_date}"
        if self._cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return cached

        day_of_week = target_date.weekday()
        is_day_off = await self.day_off_repo.is_day_off(doctor_id, target_date)
        availability = await self.availability_repo.get_by_doctor_and_day(doctor_id, day_of_week)

        if not availability:
            result = self._empty_result(doctor_id, target_date, is_day_off)
        else:
            services = await self.service_offering_repo.list_by_doctor(doctor_id)
            working_hours = self._map_working_hours(availability, is_day_off)

            result = {
                "doctor_id": str(doctor_id),
                "date": str(target_date),
                "is_day_off": is_day_off,
                "working_hours": working_hours,
                "services": self._map_services(services),
            }

        if self._cache:
            await self._cache.set(cache_key, result, ttl=_CACHE_TTL)

        return result

    def _empty_result(self, doctor_id: UUID7, target_date: date, is_day_off: bool) -> dict:
        return {
            "doctor_id": str(doctor_id),
            "date": str(target_date),
            "is_day_off": is_day_off,
            "working_hours": [],
            "services": [],
        }

    def _map_working_hours(self, availability, is_day_off: bool) -> list:
        if is_day_off or not availability:
            return []

        working_hours = []
        for avail in availability:
            hours = {
                "start_time": str(avail.start_time),
                "end_time": str(avail.end_time),
                "max_patients": avail.max_patients,
            }
            if avail.break_start and avail.break_end:
                hours["break_start"] = str(avail.break_start)
                hours["break_end"] = str(avail.break_end)
            working_hours.append(hours)
        return working_hours

    def _map_services(self, services) -> list:
        return [
            {
                "id": str(s.id),
                "service_name": s.service_name,
                "duration_minutes": s.duration_minutes,
                "fee": s.fee,
            }
            for s in services
            if s.is_active
        ]
