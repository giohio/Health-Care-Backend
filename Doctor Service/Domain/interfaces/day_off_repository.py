from abc import ABC, abstractmethod
from datetime import date

from uuid_extension import UUID7


class IDayOffRepository(ABC):
    @abstractmethod
    async def create(self, doctor_id: UUID7, off_date: date, reason: str = None):
        pass

    @abstractmethod
    async def delete(self, doctor_id: UUID7, off_date: date):
        pass

    @abstractmethod
    async def is_day_off(self, doctor_id: UUID7, off_date: date) -> bool:
        pass
