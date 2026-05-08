from enum import Enum


class Department(str, Enum):
    RESPIRATORY   = "respiratory"
    DERMATOLOGY   = "dermatology"
    NEUROLOGY     = "neurology"
    OPHTHALMOLOGY = "ophthalmology"
    CARDIOLOGY    = "cardiology"
    NEPHROLOGY    = "nephrology"
    HEMATOLOGY    = "hematology"
    ENDOCRINOLOGY = "endocrinology"
    INTERNAL      = "internal_medicine"
    RADIOLOGY     = "radiology"


class InputType(str, Enum):
    IMAGE   = "image"
    TABULAR = "tabular"
    TEXT    = "text"
    AUDIO   = "audio"


class AnalysisStatus(str, Enum):
    PENDING    = "PENDING"
    PROCESSING = "AI_PROCESSING"
    DRAFT      = "AI_DRAFT"
    FAILED     = "NEEDS_MANUAL_REVIEW"


class TriageSessionStatus(str, Enum):
    ACTIVE            = "active"           # Conversation in progress
    AI_SUGGESTED      = "ai_suggested"     # AI gave [R] but not yet auto-evaluated
    AUTO_CONFIRMED    = "auto_confirmed"   # Routine urgency — no doctor review needed
    PENDING_REVIEW    = "pending_review"   # Priority/Emergency — doctor must review
    DOCTOR_CONFIRMED  = "doctor_confirmed" # Doctor agreed with AI suggestion
    REFERRED_INTERNAL = "referred_internal"  # Doctor redirected to Internal Medicine
    ABANDONED         = "abandoned"        # Session left incomplete
