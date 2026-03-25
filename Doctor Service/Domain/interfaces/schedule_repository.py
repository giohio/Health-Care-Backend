from abc import ABC, abstractmethod
from typing import List

from Domain.entities.doctor_schedule import DoctorSchedule
from Domain.value_objects.day_of_week import DayOfWeek
from uuid_extension import UUID7


class IScheduleRepository(ABC):
    @abstractmethod
    async def save(self, schedule: DoctorSchedule) -> DoctorSchedule:
        pass

    @abstractmethod
    async def delete(self, schedule_id: UUID7) -> None:
        pass

    @abstractmethod
    async def get_by_doctor_and_day(self, doctor_id: UUID7, day: DayOfWeek) -> List[DoctorSchedule]:
        pass

    @abstractmethod
    async def list_by_doctor(self, doctor_id: UUID7) -> List[DoctorSchedule]:
        pass
