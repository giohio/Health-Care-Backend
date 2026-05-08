from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from Domain.value_objects.medication_status import MedicationStatus


@dataclass
class Medication:
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    drug_name: str
    start_date: date
    appointment_id: Optional[UUID] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    end_date: Optional[date] = None
    status: MedicationStatus = MedicationStatus.ACTIVE
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    def stop(self) -> None:
        """Discontinue an active medication before its planned end date."""
        if self.status != MedicationStatus.ACTIVE:
            raise ValueError(f"Cannot stop medication with status '{self.status}'.")
        self.status = MedicationStatus.STOPPED

    def complete(self) -> None:
        """Mark a full medication course as completed."""
        if self.status != MedicationStatus.ACTIVE:
            raise ValueError(f"Cannot complete medication with status '{self.status}'.")
        self.status = MedicationStatus.COMPLETED
