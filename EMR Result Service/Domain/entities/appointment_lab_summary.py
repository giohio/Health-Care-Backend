from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


class AppointmentSummaryStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class AppointmentLabSummary:
    id: UUID
    appointment_id: UUID
    patient_id: UUID
    status: str = AppointmentSummaryStatus.PENDING
    ai_holistic_text: Optional[str] = None
    total_results: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    doctor_conclusion: Optional[str] = None
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
