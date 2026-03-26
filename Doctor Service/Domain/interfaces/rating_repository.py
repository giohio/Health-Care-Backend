from abc import ABC, abstractmethod

from uuid_extension import UUID7


class IRatingRepository(ABC):
    @abstractmethod
    async def create(self, doctor_id: UUID7, patient_id: UUID7, rating: int, comment: str | None):
        pass

    @abstractmethod
    async def get_by_patient_and_doctor(self, patient_id: UUID7, doctor_id: UUID7):
        pass

    @abstractmethod
    async def list_by_doctor(self, doctor_id: UUID7, limit: int, offset: int):
        pass

    @abstractmethod
    async def get_average_rating(self, doctor_id: UUID7) -> float:
        pass
