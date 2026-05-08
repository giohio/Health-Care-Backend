from .symptom import router as symptom_router
from .lab import router as lab_router
from .lab_suggestion import router as lab_suggestion_router
from .emr import router as emr_router
from .triage_sessions import router as triage_sessions_router
from .lab_chat import router as lab_chat_router
from .clinical_assist import router as clinical_assist_router
from .speech import router as speech_router
from .auscultation import router as auscultation_router
from .treatment_plan import router as treatment_plan_router
from .all_labs import router as all_labs_router
from .soap import router as soap_router

__all__ = [
    "symptom_router",
    "lab_router",
    "lab_suggestion_router",
    "emr_router",
    "triage_sessions_router",
    "lab_chat_router",
    "clinical_assist_router",
    "speech_router",
    "auscultation_router",
    "treatment_plan_router",
    "all_labs_router",
    "soap_router",
]
