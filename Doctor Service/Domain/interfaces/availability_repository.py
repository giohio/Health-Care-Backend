from abc import ABC, abstractmethod
from datetime import time

from uuid_extension import UUID7


class IAvailabilityRepository(ABC):
    @abstractmethod
    async def upsert(
        self,
        doctor_id: UUID7,
        day_of_week: int,
        start_time: time,
        end_time: time,
        break_start: time | None,
        break_end: time | None,
        max_patients: int,
    ):
        pass

    @abstractmethod
    async def get_by_doctor_and_day(self, doctor_id: UUID7, day_of_week: int):
        pass

    @abstractmethod
    async def list_by_doctor(self, doctor_id: UUID7):
        pass
