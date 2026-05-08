from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from Domain.entities.diagnosis import Diagnosis
from Domain.value_objects.diagnosis_status import DiagnosisStatus


class IDiagnosisRepository(ABC):
    @abstractmethod
    async def save(self, diagnosis: Diagnosis) -> Diagnosis:
        """Persist a new diagnosis or update an existing one (upsert by id)."""

    @abstractmethod
    async def get_by_id(self, diagnosis_id: UUID) -> Optional[Diagnosis]:
        """Return a single diagnosis by its primary key, or None."""

    @abstractmethod
    async def list_by_patient(
        self,
        patient_id: UUID,
        status: Optional[DiagnosisStatus] = None,
    ) -> List[Diagnosis]:
        """List all diagnoses for a patient, optionally filtered by status.

        Results are ordered by diagnosed_at descending (most recent first).
        """
