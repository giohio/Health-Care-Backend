from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.record_source import RecordSource
from Domain.value_objects.severity import Severity


@dataclass
class Diagnosis:
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    diagnosis_name: str
    diagnosed_at: date
    appointment_id: Optional[UUID] = None
    icd10_code: Optional[str] = None
    diagnosis_detail: Optional[str] = None
    severity: Optional[Severity] = None
    status: DiagnosisStatus = DiagnosisStatus.ACTIVE
    resolved_at: Optional[date] = None
    source: RecordSource = RecordSource.DOCTOR
    created_at: Optional[datetime] = None

    def resolve(self, resolved_at: date) -> None:
        """Transition an active diagnosis to resolved."""
        if self.status == DiagnosisStatus.CHRONIC:
            raise ValueError("Chronic diagnoses cannot be directly resolved; update status explicitly.")
        if self.status == DiagnosisStatus.RESOLVED:
            raise ValueError("Diagnosis is already resolved.")
        self.status = DiagnosisStatus.RESOLVED
        self.resolved_at = resolved_at

    def mark_chronic(self) -> None:
        """Promote an active diagnosis to chronic."""
        if self.status != DiagnosisStatus.ACTIVE:
            raise ValueError(f"Only active diagnoses can be marked chronic (current: {self.status}).")
        self.status = DiagnosisStatus.CHRONIC
