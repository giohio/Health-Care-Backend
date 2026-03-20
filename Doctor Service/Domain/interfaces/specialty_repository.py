from abc import ABC, abstractmethod
from typing import List, Optional
from Domain.entities.specialty import Specialty
from uuid_extension import UUID7

class ISpecialtyRepository(ABC):
    @abstractmethod
    async def save(self, specialty: Specialty) -> Specialty:
        pass

    @abstractmethod
    async def get_by_id(self, specialty_id: UUID7) -> Optional[Specialty]:
        pass

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Specialty]:
        pass

    @abstractmethod
    async def list_all(self) -> List[Specialty]:
        pass
