from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from Domain.value_objects.note_type import NoteType


@dataclass
class ClinicalNote:
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    content: str
    appointment_id: Optional[UUID] = None
    note_type: Optional[NoteType] = None
    is_ai_generated: bool = False
    created_at: Optional[datetime] = None
