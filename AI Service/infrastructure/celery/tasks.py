import asyncio
from celery import Celery
from infrastructure.config import get_settings
from Domain.entities import LabAnalysisRequest, AllLabsAnalysisRequest
from Domain.enums import InputType, Department, AnalysisStatus
from Application.lab_analysis import LabAnalysisUseCase
from Application.all_labs_analysis import AllLabsAnalysisUseCase
from infrastructure.llm.woku_client import WokuClient
from infrastructure.clients.clinical_client import ClinicalClient
from infrastructure.clients.emr_result_client import EmrResultClient
import logging

logger = logging.getLogger(__name__)

settings   = get_settings()
celery_app = Celery(
    "ai_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery_app.conf.task_default_queue = "ai_tasks"


@celery_app.task(
    name="analyze_lab",
    bind=True,
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=10,
)
def analyze_lab_task(self, payload: dict):
    """
    Tier 2 async — fetch result, extract findings, synthesize draft, patch EMR.
    """
    async def _run():
        emr_client = EmrResultClient()
        result_id = payload["result_id"]
        auth_token = payload["auth_token"]
        x_user_id = payload.get("x_user_id")
        x_user_role = payload.get("x_user_role")

        logger.info(f"Starting AI analysis for result {result_id}")

        # 1. Fetch result details (needed for file_url etc)
        result_details = await emr_client.get_result(
            result_id, auth_token, x_user_id, x_user_role
        )

        department_val = payload.get("department") or result_details.get("department") or "internal_medicine"
        try:
            department = Department(department_val)
        except ValueError:
            department = Department.INTERNAL

        # 2. Build analysis request
        request = LabAnalysisRequest(
            result_id    = result_id,
            patient_id   = payload["patient_id"],
            file_url     = payload.get("file_url") or result_details.get("file_url"),
            input_type   = InputType(payload["input_type"]),
            department   = department,
            test_name    = payload["test_name"],
            tabular_data = payload.get("tabular_data"),
        )

        # 3. Execute analysis
        woku_client = WokuClient()
        use_case   = LabAnalysisUseCase(
            llm      = woku_client,
            gemini   = woku_client,
            clinical = ClinicalClient(),
        )

        analysis_result = await use_case.execute(request)

        # 4. Patch draft back to EMR
        draft_payload = {
            "ai_visual_findings":       analysis_result.visual_findings,
            "ai_draft_text":            analysis_result.draft_text,
            "ai_confidence":            analysis_result.confidence,
            "ai_draft_citations":       analysis_result.citations,
            "ai_model_versions":        analysis_result.model_versions,
            "requires_specialist_review": analysis_result.requires_specialist_review,
            "status":                   AnalysisStatus.DRAFT.value,
        }
        await emr_client.patch_ai_draft(
            result_id,
            draft_payload,
            x_user_id=x_user_id,
            x_user_role="service",  # internal AI→EMR callback; always service role
        )
        logger.info("Lab analysis complete for result_id=%s", result_id)

    async def _mark_manual_review():
        """Last-resort fallback: unlock the result so the doctor can verify it manually."""
        result_id = payload.get("result_id")
        if not result_id:
            return
        try:
            emr_client = EmrResultClient()
            await emr_client.patch_ai_draft(
                result_id,
                {
                    "ai_draft_text": (
                        "⚠️ AI analysis could not complete after multiple attempts. "
                        "Please review the result manually."
                    ),
                    "ai_confidence": 0.0,
                    "requires_specialist_review": True,
                    "status": AnalysisStatus.FAILED.value,
                },
                x_user_id=payload.get("x_user_id"),
                x_user_role="service",  # internal AI→EMR callback; always service role
            )
        except Exception as e:
            logger.error("Failed to mark manual review for %s: %s", result_id, e)

    # Reset the shared AsyncOpenAI client so it is re-created inside the new
    # event loop spawned by asyncio.run().  Celery fork workers inherit the
    # parent's singleton which is already bound to a closed loop, causing
    # "Event loop is closed" / APIConnectionError on the very first LLM call.
    WokuClient._shared_openai = None
    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"Task failed for {payload.get('result_id')}: {exc}")
        # Manual review on max retries
        if self.request.retries >= self.max_retries:
            WokuClient._shared_openai = None
            asyncio.run(_mark_manual_review())
        raise exc


@celery_app.task(
    name="analyze_all_labs",
    bind=True,
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=15,
)
def analyze_all_labs_task(self, payload: dict):
    """
    Celery task triggered when all lab results for an appointment are published.
    Runs a holistic cross-result synthesis and patches AppointmentLabSummary.

    payload keys:
      appointment_id, patient_id, summary_id
    """
    async def _run():
        appointment_id = payload["appointment_id"]
        patient_id     = payload["patient_id"]
        summary_id     = payload["summary_id"]

        emr_client = EmrResultClient()
        woku_client = WokuClient()
        use_case = AllLabsAnalysisUseCase(
            llm=woku_client,
            clinical=ClinicalClient(),
            emr_client=emr_client,
        )

        # Mark as PROCESSING first (best-effort)
        try:
            await emr_client.patch_holistic_summary(
                appointment_id,
                {"ai_holistic_text": "", "status": "PROCESSING"},
            )
        except Exception:
            logger.warning("Could not mark holistic summary PROCESSING for %s", appointment_id)

        request = AllLabsAnalysisRequest(
            appointment_id=appointment_id,
            patient_id=patient_id,
            summary_id=summary_id,
            results=[],  # AllLabsAnalysisUseCase fetches from EMR Result Service
        )

        result = await use_case.execute(request)

        await emr_client.patch_holistic_summary(
            appointment_id,
            {"ai_holistic_text": result.holistic_text, "status": result.status},
        )
        logger.info("Holistic analysis complete for appointment_id=%s status=%s", appointment_id, result.status)

    # Same fix: reset shared client before entering a fresh event loop.
    WokuClient._shared_openai = None
    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error("Holistic task failed for %s: %s", payload.get('appointment_id'), exc)
        raise exc
