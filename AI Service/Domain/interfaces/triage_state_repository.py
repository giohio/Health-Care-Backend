from abc import ABC, abstractmethod
from typing import Optional


class ITriageStateRepository(ABC):
    """Persistent store for per-patient triage booking state.

    Implementations must be safe for concurrent workers (e.g. Redis).
    All methods are async and keyed by patient_id.
    """

    # ── Pending slots (set when availability is shown, consumed on confirmation) ──

    @abstractmethod
    async def get_pending_slots(self, patient_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def set_pending_slots(self, patient_id: str, data: dict) -> None: ...

    @abstractmethod
    async def del_pending_slots(self, patient_id: str) -> None: ...

    # ── Recent recommendation cache (set on [R], used to route booking bypass) ──

    @abstractmethod
    async def get_recommendation(self, patient_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def set_recommendation(self, patient_id: str, data: dict) -> None: ...

    @abstractmethod
    async def del_recommendation(self, patient_id: str) -> None: ...
