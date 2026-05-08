from abc import ABC, abstractmethod
from typing import Optional

from Domain.entities import TriageSession


class ITriageSessionRepository(ABC):

    @abstractmethod
    async def save(self, session: TriageSession) -> TriageSession: ...

    @abstractmethod
    async def get_by_id(self, session_id: str) -> Optional[TriageSession]: ...

    @abstractmethod
    async def list_by_patient(self, patient_id: str) -> list[TriageSession]: ...

    @abstractmethod
    async def list_all(self, status_filter: Optional[str] = None) -> list[TriageSession]: ...
