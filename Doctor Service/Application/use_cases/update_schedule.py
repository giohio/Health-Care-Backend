from typing import List

from Application.dtos import ScheduleDTO
from Domain.entities.doctor_schedule import DoctorSchedule
from Domain.exceptions.domain_exceptions import DoctorNotFoundException
from Domain.interfaces.doctor_repository import IDoctorRepository
from Domain.interfaces.schedule_repository import IScheduleRepository
from healthai_cache import CacheClient
from uuid_extension import UUID7


class UpdateScheduleUseCase:
    def __init__(
        self,
        schedule_repo: IScheduleRepository,
        doctor_repo: IDoctorRepository,
        cache: CacheClient | None = None,
    ):
        self.schedule_repo = schedule_repo
        self.doctor_repo = doctor_repo
        self._cache = cache

    async def execute(self, doctor_id: UUID7, dtos: List[ScheduleDTO]) -> List[ScheduleDTO]:
        # 1. Verify doctor exists
        doctor = await self.doctor_repo.get_by_id(doctor_id)
        if not doctor:
            raise DoctorNotFoundException(doctor_id)

        existing = await self.schedule_repo.list_by_doctor(doctor_id)
        for s in existing:
            await self.schedule_repo.delete(s.id)

        new_schedules = []
        for dto in dtos:
            schedule = DoctorSchedule(
                id=dto.id or UUID7(),
                doctor_id=doctor_id,
                day_of_week=dto.day_of_week,
                start_time=dto.start_time,
                end_time=dto.end_time,
                slot_duration_minutes=dto.slot_duration_minutes,
            )
            saved = await self.schedule_repo.save(schedule)
            new_schedules.append(
                ScheduleDTO.model_validate(
                    {
                        "id": str(saved.id),
                        "doctor_id": str(saved.doctor_id),
                        "day_of_week": saved.day_of_week,
                        "start_time": saved.start_time,
                        "end_time": saved.end_time,
                        "slot_duration_minutes": saved.slot_duration_minutes,
                    }
                )
            )

        if self._cache:
            await self._cache.delete(
                f"doctor:schedule:{doctor_id}",
                f"doctor:availability:{doctor_id}",
            )
            await self._cache.delete_pattern(f"doctor:enhanced_schedule:{doctor_id}:*")

        return new_schedules
