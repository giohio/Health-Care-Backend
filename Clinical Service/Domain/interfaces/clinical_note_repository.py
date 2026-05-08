from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from Domain.entities.clinical_note import ClinicalNote


class IClinicalNoteRepository(ABC):
    @abstractmethod
    async def save(self, note: ClinicalNote) -> ClinicalNote:
        """Persist a new clinical note."""

    @abstractmethod
    async def get_by_id(self, note_id: UUID) -> Optional[ClinicalNote]:
        """Return a single clinical note by its primary key, or None."""

    @abstractmethod
    async def update_content(self, note_id: UUID, content: str) -> Optional[ClinicalNote]:
        """Update the content of an existing note in-place. Returns None if not found."""

    @abstractmethod
    async def list_by_patient(
        self,
        patient_id: UUID,
        appointment_id: Optional[UUID] = None,
    ) -> List[ClinicalNote]:
        """List clinical notes for a patient.

        When appointment_id is provided, results are further filtered to that
        specific appointment. Results are ordered by created_at descending.
        """
