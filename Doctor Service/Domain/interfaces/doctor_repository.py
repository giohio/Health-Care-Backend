from abc import ABC, abstractmethod
from datetime import time
from typing import List, Optional

from Domain.entities.doctor import Doctor
from uuid_extension import UUID7


class IDoctorRepository(ABC):
    @abstractmethod
    async def save(self, doctor: Doctor) -> Doctor:
        pass

    @abstractmethod
    async def get_by_id(self, user_id: UUID7) -> Optional[Doctor]:
        pass

    @abstractmethod
    async def list_by_specialty(self, specialty_id: UUID7) -> List[Doctor]:
        pass

    @abstractmethod
    async def search_available(self, specialty_id: UUID7, day_of_week: int, time_slot: time) -> List[Doctor]:
        pass

    @abstractmethod
    async def update_average_rating(self, doctor_id: UUID7, average_rating: float):
        pass
