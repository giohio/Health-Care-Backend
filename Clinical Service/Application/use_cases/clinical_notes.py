import uuid
from typing import List, Optional

from Application.dtos import ClinicalNoteResponse, CreateClinicalNoteRequest
from Domain.entities.clinical_note import ClinicalNote
from Domain.interfaces.clinical_note_repository import IClinicalNoteRepository


class CreateClinicalNoteUseCase:
    """Persist a new clinical note written by a doctor (or AI-generated)."""

    def __init__(self, note_repo: IClinicalNoteRepository):
        self.note_repo = note_repo

    async def execute(self, request: CreateClinicalNoteRequest) -> ClinicalNoteResponse:
        note = ClinicalNote(
            id=uuid.uuid4(),
            patient_id=request.patient_id,
            doctor_id=request.doctor_id,
            appointment_id=request.appointment_id,
            note_type=request.note_type,
            content=request.content,
            is_ai_generated=request.is_ai_generated,
        )
        saved = await self.note_repo.save(note)
        return ClinicalNoteResponse.model_validate(saved, from_attributes=True)


class UpdateClinicalNoteUseCase:
    """Update the content of an existing clinical note in-place."""

    def __init__(self, note_repo: IClinicalNoteRepository):
        self.note_repo = note_repo

    async def execute(self, note_id: uuid.UUID, content: str) -> Optional[ClinicalNoteResponse]:
        updated = await self.note_repo.update_content(note_id, content)
        if updated is None:
            return None
        return ClinicalNoteResponse.model_validate(updated, from_attributes=True)


class ListClinicalNotesUseCase:
    """List clinical notes for a patient, with optional appointment filter."""

    def __init__(self, note_repo: IClinicalNoteRepository):
        self.note_repo = note_repo

    async def execute(
        self,
        patient_id: uuid.UUID,
        appointment_id: Optional[uuid.UUID] = None,
    ) -> List[ClinicalNoteResponse]:
        notes = await self.note_repo.list_by_patient(patient_id, appointment_id=appointment_id)
        return [ClinicalNoteResponse.model_validate(n, from_attributes=True) for n in notes]
