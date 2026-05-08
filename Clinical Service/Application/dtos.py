from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.medication_status import MedicationStatus
from Domain.value_objects.note_type import NoteType
from Domain.value_objects.record_source import RecordSource
from Domain.value_objects.severity import Severity
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Diagnosis DTOs
# ---------------------------------------------------------------------------


class CreateDiagnosisRequest(BaseModel):
    patient_id: UUID
    doctor_id: UUID
    diagnosis_name: str
    diagnosed_at: date
    appointment_id: Optional[UUID] = None
    icd10_code: Optional[str] = None
    diagnosis_detail: Optional[str] = None
    severity: Optional[Severity] = None
    status: DiagnosisStatus = DiagnosisStatus.ACTIVE
    source: RecordSource = RecordSource.DOCTOR


class UpdateDiagnosisRequest(BaseModel):
    status: Optional[DiagnosisStatus] = None
    resolved_at: Optional[date] = None
    diagnosis_detail: Optional[str] = None
    severity: Optional[Severity] = None
    icd10_code: Optional[str] = None


class DiagnosisResponse(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    appointment_id: Optional[UUID]
    icd10_code: Optional[str]
    diagnosis_name: str
    diagnosis_detail: Optional[str]
    severity: Optional[Severity]
    status: DiagnosisStatus
    diagnosed_at: date
    resolved_at: Optional[date]
    source: RecordSource
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Medication DTOs
# ---------------------------------------------------------------------------


class CreateMedicationRequest(BaseModel):
    patient_id: UUID
    doctor_id: UUID
    drug_name: str
    start_date: date
    appointment_id: Optional[UUID] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None


class UpdateMedicationStatusRequest(BaseModel):
    status: MedicationStatus
    end_date: Optional[date] = None


class MedicationResponse(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    appointment_id: Optional[UUID]
    drug_name: str
    dosage: Optional[str]
    frequency: Optional[str]
    route: Optional[str]
    start_date: date
    end_date: Optional[date]
    status: MedicationStatus
    notes: Optional[str]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Clinical Note DTOs
# ---------------------------------------------------------------------------


class CreateClinicalNoteRequest(BaseModel):
    # patient_id is injected from the URL path parameter by the route, so it is
    # optional in the request body to avoid a Pydantic 422 before injection.
    patient_id: Optional[UUID] = None
    doctor_id: UUID
    content: str
    appointment_id: Optional[UUID] = None
    note_type: Optional[NoteType] = None
    is_ai_generated: bool = False


class UpdateClinicalNoteContentRequest(BaseModel):
    content: str


class ClinicalNoteResponse(BaseModel):
    id: UUID
    patient_id: UUID
    doctor_id: UUID
    appointment_id: Optional[UUID]
    note_type: Optional[NoteType]
    content: str
    is_ai_generated: bool
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Patient Summary DTO (composite view)
# ---------------------------------------------------------------------------


class PatientSummaryResponse(BaseModel):
    patient_id: UUID
    diagnoses: List[DiagnosisResponse]
    medications: List[MedicationResponse]
    allergies: List[str]
    vitals_latest: Optional[Dict[str, Any]]


class VaccinationResponse(BaseModel):
    id: UUID
    patient_id: UUID
    vaccine_name: str
    date_administered: date
    next_due_date: Optional[date]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
