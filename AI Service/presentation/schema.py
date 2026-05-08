from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum


class XrayType(str, Enum):
    BONE = "bone_xray"
    ABDOMINAL = "abdominal_xray"
    SKULL = "skull_xray"
    SPINE = "spine_xray"
    CHEST = "chest_xray"

# ── Triage / Symptom Check ──────────────────────────────────────────────────

class SymptomCheckInput(BaseModel):
    patient_id: str = Field(..., description="UUID of the patient")
    symptoms:   str = Field(..., min_length=1, max_length=2000,
                            description="Current patient message (description or follow-up answer)")
    duration:   Optional[str] = None   # only meaningful on first turn
    severity:   Optional[str] = None   # only meaningful on first turn
    booking_requested: bool = Field(
        default=False,
        description="Set to true when patient wants to book an appointment after [R] recommendation. "
                    "The 'symptoms' field then carries the preferred date/time.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Existing triage session UUID. Omit to start a new session.",
    )


# ── Triage Session responses ────────────────────────────────────────────────

class TriageSessionResponse(BaseModel):
    id:                   str
    patient_id:           str
    patient_name:         Optional[str] = None  # fetched from patient_service
    status:               str
    messages:             list[dict]
    suggested_department: Optional[str] = None
    urgency_level:        Optional[str] = None
    doctor_id:            Optional[str] = None
    final_department:     Optional[str] = None
    doctor_notes:         Optional[str] = None
    created_at:           Optional[str] = None
    updated_at:           Optional[str] = None
    completed_at:         Optional[str] = None
    appointment_id:        Optional[str] = None  # set after patient books via AI
    pending_booking:       Optional[dict] = None  # booking request awaiting doctor confirmation


class TriageSessionListResponse(BaseModel):
    sessions: list[TriageSessionResponse]
    total:    int


# ── Doctor review ───────────────────────────────────────────────────────────

class DoctorConfirmInput(BaseModel):
    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optional remarks from the doctor.",
    )


class DoctorReferInput(BaseModel):
    notes: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Reason for redirecting to Internal Medicine.",
    )


class TriageSummaryResponse(BaseModel):
    """AI-generated clinical summary of a triage session, intended for doctor review."""
    chief_complaint:        str                 = ""
    reported_symptoms:      list[str]           = Field(default_factory=list)
    duration:               str                 = ""
    severity:              str                 = ""
    suspected_conditions:   list[str]           = Field(default_factory=list)
    department_reasoning:   str                 = ""
    recommended_department: str                 = ""
    urgency_level:         str                 = ""
    patient_description:    str                 = ""
    clinical_reasoning:    str                 = ""
    # Session metadata echoed back for convenience
    session_id:             Optional[str]       = None
    triage_status:          Optional[str]       = None


# ── Lab analysis ────────────────────────────────────────────────────────────

class TriggerLabAnalysisInput(BaseModel):
    result_id:    str
    patient_id:   str
    file_url:     Optional[str] = None  # None for manual/tabular entries
    input_type:   str   # "image" | "tabular"
    department:   str
    test_name:    str
    tabular_data: Optional[dict] = None
    auth_token:   str   # passed through for internal patch call


# ── EMR summary ─────────────────────────────────────────────────────────────

class EmrSummaryInput(BaseModel):
    patient_id: str
    language:   str = "en"  # 'vi' or 'en'


class SoapDraftInput(BaseModel):
    patient_id: str
    triage_session_id: Optional[str] = None



# ── Lab Q&A Chat ──────────────────────────────────────────────────────────────

class LabChatInput(BaseModel):
    question:   str = Field(..., min_length=1, max_length=2000)
    patient_id: Optional[str] = Field(
        default=None,
        description="Include to inject clinical context from the patient's record.",
    )
    department: Optional[str] = Field(
        default=None,
        description="Limit RAG retrieval to this department (e.g. 'cardiology').",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Existing chat session UUID. Omit to start a new session.",
    )


# ── Clinical Decision Support ─────────────────────────────────────────────────

class ClinicalAssistInput(BaseModel):
    question:   str = Field(..., min_length=1, max_length=4000,
                            description="Clinical question from the doctor.")
    patient_id: Optional[str] = Field(
        default=None,
        description="Include to inject the patient's clinical record into reasoning.",
    )
    department: Optional[str] = Field(
        default=None,
        description="Limit RAG retrieval to this department.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Existing chat session UUID. Omit to start a new session.",
    )


# ── Speech / Audio ────────────────────────────────────────────────────────────

class TtsInput(BaseModel):
    text:     str = Field(..., min_length=1, max_length=4000)
    language: Literal["vi", "en"] = "en"
    voice:    Optional[str] = Field(
        default=None,
        description="Edge-TTS voice name. Defaults to vi-VN-HoaiMyNeural (vi) or en-US-JennyNeural (en).",
    )


class TranscriptionResponse(BaseModel):
    text:     str
    language: str


# ── Auscultation ──────────────────────────────────────────────────────────────

class AuscultationInput(BaseModel):
    patient_id:  str
    sound_type:  Literal["lung_sounds", "heart_sounds"]
    department:  Literal["respiratory", "cardiology"]
    language:    Literal["vi", "en"] = "en"
    auth_token:  str = Field(..., description="Bearer token for inter-service calls.")


# ── Lab Test Suggestions ──────────────────────────────────────────────────────

class LabSuggestionInput(BaseModel):
    symptoms:   str = Field(..., min_length=1, max_length=2000,
                            description="Patient symptoms or clinical presentation.")
    patient_id: Optional[str] = Field(
        default=None,
        description="Include to inject clinical history into suggestions.",
    )
    department: Optional[str] = Field(
        default=None,
        description="Restrict suggestions to a specific department (e.g. 'cardiology').",
    )


class TreatmentPlanInput(BaseModel):
    lab_summary: str = Field(..., min_length=1, max_length=4000,
                             description="Lab result text or AI-generated summary to base the plan on.")
    patient_id:  Optional[str] = Field(
        default=None,
        description="Include to inject full clinical history into the plan.",
    )
    symptoms:    Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Presenting symptoms or chief complaint (optional context).",
    )
