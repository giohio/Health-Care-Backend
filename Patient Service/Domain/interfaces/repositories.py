from abc import ABC, abstractmethod

from Domain.entities import PatientHealthBackground, PatientProfile
from uuid_extension import UUID7


class IPatientProfileRepository(ABC):
    @abstractmethod
    async def create(self, profile: PatientProfile) -> PatientProfile:
        pass

    @abstractmethod
    async def get_by_id(self, profile_id: UUID7) -> PatientProfile | None:
        pass

    @abstractmethod
    async def get_by_user_id(self, user_id: UUID7) -> PatientProfile | None:
        pass

    @abstractmethod
    async def update(self, profile_id: UUID7, **fields) -> PatientProfile:
        pass

    @abstractmethod
    async def delete(self, profile_id: UUID7) -> bool:
        pass


class IPatientHealthRepository(ABC):
    @abstractmethod
    async def create(self, background: PatientHealthBackground) -> PatientHealthBackground:
        pass

    @abstractmethod
    async def get_by_patient_id(self, patient_id: UUID7) -> PatientHealthBackground | None:
        pass

    @abstractmethod
    async def update(self, patient_id: UUID7, **fields) -> PatientHealthBackground:
        pass
