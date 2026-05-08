from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from Domain.entities.medication import Medication
from Domain.value_objects.medication_status import MedicationStatus


class IMedicationRepository(ABC):
    @abstractmethod
    async def save(self, medication: Medication) -> Medication:
        """Persist a new medication or update an existing one (upsert by id)."""

    @abstractmethod
    async def get_by_id(self, medication_id: UUID) -> Optional[Medication]:
        """Return a single medication by its primary key, or None."""

    @abstractmethod
    async def list_by_patient(
        self,
        patient_id: UUID,
        status: Optional[MedicationStatus] = None,
    ) -> List[Medication]:
        """List all medications for a patient, optionally filtered by status.

        Results are ordered by start_date descending.
        """
