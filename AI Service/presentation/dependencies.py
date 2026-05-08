from Application.symptom_check import SymptomCheckUseCase
from Application.emr_summary import EmrSummaryUseCase
from Application.soap_draft import SoapDraftUseCase
from Application.lab_chat import LabChatUseCase
from Application.lab_suggestion import LabSuggestionUseCase
from Application.clinical_assist import ClinicalAssistUseCase
from Application.auscultation_analysis import AuscultationAnalysisUseCase
from Application.treatment_plan import TreatmentPlanUseCase
from infrastructure.llm.woku_client import WokuClient
from infrastructure.llm.gemini_client import GeminiClient
from infrastructure.clients.clinical_client import ClinicalClient
from infrastructure.clients.emr_result_client import EmrResultClient
from infrastructure.retriever.qdrant_retriever import QdrantRetriever
from infrastructure.repositories.redis_triage_state import RedisTriageStateRepository
from infrastructure.config import get_settings

# ---------------------------------------------------------------------------
# Per-use-case WokuClient singletons.
# All share the same underlying AsyncOpenAI connection pool (see WokuClient._shared_openai)
# but each targets its own model, configurable via .env overrides.
# ---------------------------------------------------------------------------
def _make_clients():
    s = get_settings()
    fallback = s.WOKU_MODEL_FAST or s.WOKU_MODEL
    return {
        # triage and clinical get fallback so a rate-limited pro model falls back to a fast model
        "triage":   WokuClient(model=s.WOKU_MODEL_TRIAGE   or s.WOKU_MODEL, fallback_model=fallback),
        "clinical": WokuClient(model=s.WOKU_MODEL_CLINICAL  or s.WOKU_MODEL, fallback_model=fallback),
        "lab_chat": WokuClient(model=s.WOKU_MODEL_LAB_CHAT  or s.WOKU_MODEL),
        "emr":      WokuClient(model=s.WOKU_MODEL_EMR       or s.WOKU_MODEL),
        "fast":     WokuClient(model=s.WOKU_MODEL_FAST      or s.WOKU_MODEL),
    }

_retriever = QdrantRetriever()
_gemini_vision_client = GeminiClient()
_triage_state = RedisTriageStateRepository()
_clients = _make_clients()


def get_symptom_usecase() -> SymptomCheckUseCase:
    return SymptomCheckUseCase(
        llm=_clients["triage"],
        clinical=ClinicalClient(),
        retriever=_retriever,
        state=_triage_state,
    )


def get_emr_summary_usecase() -> EmrSummaryUseCase:
    return EmrSummaryUseCase(
        llm=_clients["emr"],
        clinical=ClinicalClient(),
        emr_result=EmrResultClient(),
        retriever=_retriever,
    )


def get_lab_chat_usecase() -> LabChatUseCase:
    return LabChatUseCase(
        llm=_clients["lab_chat"],
        clinical=ClinicalClient(),
        retriever=_retriever,
    )


def get_clinical_assist_usecase() -> ClinicalAssistUseCase:
    return ClinicalAssistUseCase(
        llm=_clients["clinical"],
        clinical=ClinicalClient(),
        retriever=_retriever,
    )


def get_lab_suggestion_usecase() -> LabSuggestionUseCase:
    return LabSuggestionUseCase(
        llm=_clients["fast"],
        clinical=ClinicalClient(),
    )


def get_auscultation_usecase() -> AuscultationAnalysisUseCase:
    return AuscultationAnalysisUseCase(
        llm=_clients["emr"],
        gemini=_gemini_vision_client,
        clinical=ClinicalClient(),
        retriever=_retriever,
    )


def get_treatment_plan_usecase() -> TreatmentPlanUseCase:
    return TreatmentPlanUseCase(
        llm=_clients["fast"],
        clinical=ClinicalClient(),
    )


def get_soap_draft_usecase() -> SoapDraftUseCase:
    return SoapDraftUseCase(
        llm=_clients["emr"],
        clinical=ClinicalClient(),
        emr_result=EmrResultClient(),
    )