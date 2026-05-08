from abc import ABC, abstractmethod

from Domain.entities import PatientContext


class IClinicalClient(ABC):
    """Abstract interface for fetching patient context from the Clinical Service."""

    @abstractmethod
    async def get_patient_context(
        self,
        patient_id: str,
        x_user_id: str,
        x_user_role: str,
    ) -> PatientContext:
        """Fetch a patient's summary and return it as a PatientContext domain entity."""
        ...
