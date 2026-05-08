from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType
from pydantic import BaseModel, ConfigDict, model_validator


# ---------------------------------------------------------------------------
# Lab Order DTOs
# ---------------------------------------------------------------------------


class CreateLabOrderRequest(BaseModel):
    patient_id: UUID
    doctor_id: UUID
    test_name: str
    appointment_id: Optional[UUID] = None
    test_type: Optional[TestType] = None
    department: Optional[str] = None
    instructions: Optional[str] = None
    priority: OrderPriority = OrderPriority.ROUTINE
    fee: int = 0


class LabOrderResponse(BaseModel):
    id: UUID
    patient_id: UUID
    patient_name: Optional[str] = None
    doctor_id: UUID
    appointment_id: Optional[UUID]
    test_name: str
    test_type: Optional[TestType]
    department: Optional[str]
    instructions: Optional[str]
    priority: OrderPriority
    fee: int
    ordered_at: Optional[datetime]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Lab Order Template DTOs
# ---------------------------------------------------------------------------


class TemplateTestItemRequest(BaseModel):
    test_name: str
    test_type: Optional[str] = None    # TestType enum value string
    instructions: Optional[str] = None
    priority: str = "routine"           # OrderPriority enum value string


class CreateLabOrderTemplateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    department: Optional[str] = None
    test_items: List[TemplateTestItemRequest]


class TemplateTestItemResponse(BaseModel):
    test_name: str
    test_type: Optional[str]
    instructions: Optional[str]
    priority: str

    model_config = ConfigDict(from_attributes=True)


class LabOrderTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    department: Optional[str]
    test_items: List[Dict[str, Any]]
    creator_type: str
    creator_id: Optional[UUID]
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class CreateLabOrderFromTemplateRequest(BaseModel):
    template_id: UUID
    patient_id: UUID
    doctor_id: UUID
    appointment_id: Optional[UUID] = None


# ---------------------------------------------------------------------------
# Lab Result DTOs
# ---------------------------------------------------------------------------


class ManualLabEntry(BaseModel):
    """A single manually-entered lab value."""
    test_name: str
    value: str  # string — supports qualitative values like ">500" or "Reactive"
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    flag: Optional[Literal["H", "L", "N", "C"]] = None


class CreateLabResultRequest(BaseModel):
    """Submitted when a lab file is uploaded or results are entered manually."""
    order_id: UUID
    patient_id: UUID
    doctor_id: UUID

    # Nullable when file_type == "manual"
    file_url: Optional[str] = None
    file_type: str  # "pdf"|"png"|"jpg"|"jpeg"|"dicom"|"manual"|"other"

    # Manual entry fields (required when file_type == "manual")
    manual_entries: Optional[List[ManualLabEntry]] = None
    notes: Optional[str] = None  # free-text clinical note from doctor

    @model_validator(mode="after")
    def _validate_file_or_manual(self) -> "CreateLabResultRequest":
        if self.file_type == "manual":
            if self.file_url is not None:
                raise ValueError("file_url must be null or absent when file_type is 'manual'")
            if not self.manual_entries:
                raise ValueError("manual_entries must have at least 1 item when file_type is 'manual'")
        else:
            if not self.file_url:
                raise ValueError("file_url is required when file_type is not 'manual'")
        return self


class UpdateAIDraftRequest(BaseModel):
    """Payload POSTed by the AI Service Celery task after lab analysis completes."""
    ai_visual_findings: Optional[Dict[str, Any]] = None
    ai_draft_text: str
    ai_confidence: float
    ai_draft_citations: Optional[Any] = None  # AI Service returns list[str]; accept any shape
    ai_model_versions: Optional[Dict[str, Any]] = None
    requires_specialist_review: bool = False


class VerifyLabResultRequest(BaseModel):
    """Doctor verifies and optionally overrides AI draft before publishing."""
    doctor_notes: Optional[str] = None
    published_text: Optional[str] = None
    published_findings: Optional[List[Dict[str, Any]]] = None


class LabResultResponse(BaseModel):
    id: UUID
    order_id: UUID
    patient_id: UUID
    patient_name: Optional[str] = None
    doctor_id: UUID
    status: LabResultStatus
    file_url: Optional[str]
    file_type: Optional[str]

    # Specialist review routing
    reviewer_doctor_id: Optional[UUID] = None
    required_specialty: Optional[str] = None

    # Raw input (manual entries) — used by retry-ai; never overwritten by AI
    raw_input_json: Optional[str] = None

    # AI draft — hidden from patients; visible to doctors/admins
    ai_visual_findings: Optional[Any] = None  # can be list or dict
    ai_draft_text: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_processed_at: Optional[datetime] = None

    # Published content
    published_text: Optional[str]
    published_findings: Optional[Any] = None  # can be list or dict
    published_at: Optional[datetime]

    doctor_notes: Optional[str]
    verified_by: Optional[UUID]
    verified_at: Optional[datetime]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class PatientLabResultResponse(BaseModel):
    """Stripped-down view returned to patients — no raw AI internals."""
    id: UUID
    order_id: UUID
    status: LabResultStatus
    published_text: Optional[str]
    published_findings: Optional[List[Dict[str, Any]]] = None
    published_at: Optional[datetime]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class FileUploadResponse(BaseModel):
    """Returned by POST /upload."""
    url: str
    file_type: str
    original_filename: str
    size_bytes: int


# ---------------------------------------------------------------------------
# Appointment Holistic Summary DTOs
# ---------------------------------------------------------------------------


class AppointmentLabSummaryResponse(BaseModel):
    """Returned to the frontend for the combined AI analysis of a full visit."""
    id: UUID
    appointment_id: UUID
    patient_id: UUID
    status: str          # PENDING | PROCESSING | DONE | FAILED
    ai_holistic_text: Optional[str] = None
    total_results: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    doctor_conclusion: Optional[str] = None
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UpdateHolisticSummaryRequest(BaseModel):
    """Payload POSTed by the AI Service after holistic analysis completes."""
    ai_holistic_text: str
    status: str = "DONE"   # DONE | FAILED


class ReviewHolisticSummaryRequest(BaseModel):
    """Payload sent by the doctor to add their clinical conclusion."""
    doctor_conclusion: str
