import uuid
from abc import ABC, abstractmethod
from typing import List

from Domain.entities.vaccination import Vaccination


class IVaccinationRepository(ABC):
    @abstractmethod
    async def save(self, vaccination: Vaccination) -> Vaccination:
        raise NotImplementedError

    @abstractmethod
    async def list_by_patient(self, patient_id: uuid.UUID) -> List[Vaccination]:
        raise NotImplementedError