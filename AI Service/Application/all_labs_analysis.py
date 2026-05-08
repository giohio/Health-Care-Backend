"""AllLabsAnalysisUseCase — holistic cross-result synthesis for a completed appointment."""
import logging
from typing import Optional

from Domain.entities import AllLabsAnalysisRequest, AllLabsAnalysisResult
from Domain.interfaces import ILLMClient, IClinicalClient, IEmrResultClient
from Domain.prompts import ALL_LABS_SYNTHESIS_SYSTEM, build_all_labs_prompt

logger = logging.getLogger(__name__)


class AllLabsAnalysisUseCase:
    """
    Fetches all PUBLISHED results for an appointment from EMR Result Service,
    then calls the LLM to produce a unified holistic clinical commentary.
    Called from Celery task — NOT from HTTP request directly.
    """

    def __init__(
        self,
        llm: ILLMClient,
        clinical: IClinicalClient,
        emr_client: IEmrResultClient,
    ):
        self._llm = llm
        self._clinical = clinical
        self._emr = emr_client

    async def execute(self, request: AllLabsAnalysisRequest) -> AllLabsAnalysisResult:
        # 1. Fetch patient context
        try:
            context = await self._clinical.get_patient_context(
                request.patient_id,
                x_user_id=request.patient_id,
                x_user_role="doctor",
            )
        except Exception:
            logger.warning(
                "Could not fetch patient context for holistic analysis appointment=%s",
                request.appointment_id,
            )
            context = None

        # 2. Fetch published results if not pre-loaded in request
        results = request.results
        if not results:
            try:
                results = await self._emr.get_published_results_for_appointment(
                    request.appointment_id
                )
            except Exception:
                logger.warning(
                    "Could not fetch published results for appointment=%s", request.appointment_id
                )
                results = []

        if not results:
            return AllLabsAnalysisResult(
                summary_id=request.summary_id,
                holistic_text=(
                    "⚠️ AI HOLISTIC ANALYSIS — REQUIRES PHYSICIAN REVIEW AND APPROVAL\n\n"
                    "No published lab results were available for holistic analysis. "
                    "Please review individual results manually."
                ),
                status="FAILED",
            )

        # 3. Build prompt
        if context:
            prompt = build_all_labs_prompt(results, context)
        else:
            # Minimal fallback context object
            class _MinCtx:
                full_name = "Unknown"
                age = None
                gender = None
                active_diagnoses = []
                current_medications = []
                allergies = ""
                chronic_conditions = ""
                recent_notes = []

            prompt = build_all_labs_prompt(results, _MinCtx())

        # 4. Call LLM
        try:
            holistic_text = await self._llm.complete(
                system_prompt=ALL_LABS_SYNTHESIS_SYSTEM,
                user_prompt=prompt,
            )
        except Exception:
            logger.exception(
                "LLM call failed for holistic analysis appointment=%s", request.appointment_id
            )
            return AllLabsAnalysisResult(
                summary_id=request.summary_id,
                holistic_text=(
                    "⚠️ AI HOLISTIC ANALYSIS — REQUIRES PHYSICIAN REVIEW AND APPROVAL\n\n"
                    "AI synthesis could not be completed. Please review individual results manually."
                ),
                status="FAILED",
            )

        return AllLabsAnalysisResult(
            summary_id=request.summary_id,
            holistic_text=holistic_text,
            status="DONE",
        )
