from abc import ABC, abstractmethod
from typing import List, Dict, Any
from uuid_extension import UUID7
from datetime import time

class IDoctorServiceClient(ABC):
    @abstractmethod
    async def get_available_doctors(self, specialty_id: UUID7, day_of_week: int, time_slot: time) -> List[Dict[str, Any]]:
        """
        Calls Doctor Service to find doctors working in a specialty on a specific day/time.
        Returns a list of doctor info (user_id, full_name, etc.)
        """
        pass

    @abstractmethod
    async def get_schedule(self, doctor_id: str) -> dict | None:
        """Return doctor schedule payload or None when unavailable."""
        pass

    @abstractmethod
    async def get_type_config(self, specialty_id: str, appointment_type: str) -> dict | None:
        """Return appointment type config (duration/buffer) or None."""
        pass

    @abstractmethod
    async def get_patient_full_context(self, patient_id: str) -> dict | None:
        """Return patient full context payload for queue enrichment."""
        pass
