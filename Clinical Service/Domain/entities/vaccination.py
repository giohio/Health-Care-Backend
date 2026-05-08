from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from uuid import UUID


@dataclass
class Vaccination:
    id: UUID
    patient_id: UUID
    vaccine_name: str
    date_administered: date
    next_due_date: Optional[date] = None
    created_at: Optional[datetime] = None