from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from .enums import Department, InputType, TriageSessionStatus


@dataclass
class ConversationTurn:
    """A single turn in the triage conversation."""
    role: str    # "patient" | "assistant"
    content: str


@dataclass
class PatientContext:
    """Patient history fetched from clinical_service + patient_service. Passed to every LLM call."""
    patient_id:          str
    full_name:           str
    age:                 Optional[int]
    gender:              Optional[str]
    active_diagnoses:    list[str] = field(default_factory=list)
    current_medications: list[str] = field(default_factory=list)
    allergies:           str = ""
    chronic_conditions:  str = ""
    # Health record vitals
    blood_type:          Optional[str] = None
    height_cm:           Optional[float] = None
    weight_kg:           Optional[float] = None
    blood_pressure:      Optional[str] = None
    heart_rate_bpm:      Optional[int] = None
    temperature_celsius: Optional[float] = None
    oxygen_saturation:   Optional[int] = None
    recent_notes:        list[str] = field(default_factory=list)


@dataclass
class SymptomCheckRequest:
    patient_id:           str
    symptoms:             str   # current patient message
    duration:             Optional[str] = None
    severity:             Optional[str] = None
    conversation_history: list[ConversationTurn] = field(default_factory=list)
    booking_requested:    bool = False  # patient wants to book after [R] recommendation
    session_id:           Optional[str] = None  # used by tool handler for booking
    suggested_department: Optional[str] = None   # extracted from [R] recommendation
    urgency_level:        Optional[str] = None   # extracted from [R] recommendation


@dataclass
class SymptomCheckResult:
    suggested_departments: list[str]
    triage_notes:          str
    urgency_level:         str
    disclaimer:            str


@dataclass
class LabAnalysisRequest:
    result_id:    str
    patient_id:   str
    file_url:     Optional[str]
    input_type:   InputType
    department:   Department
    test_name:    str
    tabular_data: Optional[dict] = None


@dataclass
class LabAnalysisResult:
    result_id:                   str
    visual_findings:             Optional[dict]
    draft_text:                  str
    confidence:                  float
    citations:                   list[str]
    model_versions:              dict
    requires_specialist_review:  bool = False


@dataclass
class EmrSummaryRequest:
    patient_id: str
    doctor_id:  str
    language:   str = "en"  # 'vi' or 'en' — matches doctor's UI language


@dataclass
class EmrSummaryResult:
    summary_text:    str
    key_concerns:    list[str]
    recommendations: list[str]
    disclaimer:      str


@dataclass
class AllLabsAnalysisRequest:
    """Holistic cross-result analysis for an appointment (all results published)."""
    appointment_id: str
    patient_id:     str
    summary_id:     str    # AppointmentLabSummary.id to PATCH on completion
    results:        list[dict]  # list of {test_name, ai_draft_text, ai_visual_findings, published_text}


@dataclass
class AllLabsAnalysisResult:
    summary_id:    str
    holistic_text: str
    status:        str = "DONE"  # DONE | FAILED


@dataclass
class TriageSession:
    """
    Persisted record of a single patient triage conversation.

    ``messages`` is the full ordered conversation list:
      [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    Patient turns have role="user"; AI turns have role="assistant".
    """

    id:                   str
    patient_id:           str
    status:               TriageSessionStatus
    messages:             list[dict] = field(default_factory=list)
    suggested_department: Optional[str]  = None
    urgency_level:        Optional[str]  = None
    doctor_id:            Optional[str]  = None
    final_department:     Optional[str]  = None
    doctor_notes:         Optional[str]  = None
    created_at:           Optional[datetime] = None
    updated_at:           Optional[datetime] = None
    completed_at:         Optional[datetime] = None
    # AI-guided booking fields
    appointment_id:        Optional[str]  = None  # set after patient books via AI
    pending_booking:       Optional[dict] = None  # booking request pending doctor confirmation


@dataclass
class ChatSession:
    """
    Persisted multi-turn conversation for lab_chat and clinical_assist endpoints.

    ``messages`` stores ordered turns:
      [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]

    ``session_type`` is one of: "lab_chat" | "clinical_assist"
    ``user_role``    is one of: "patient"  | "doctor" | "admin"
    """

    id:           str
    user_id:      str
    user_role:    str               # "patient" | "doctor" | "admin"
    session_type: str               # "lab_chat" | "clinical_assist"
    messages:     list[dict] = field(default_factory=list)
    patient_id:   Optional[str]      = None
    department:   Optional[str]      = None
    created_at:   Optional[datetime] = None
    updated_at:   Optional[datetime] = None
