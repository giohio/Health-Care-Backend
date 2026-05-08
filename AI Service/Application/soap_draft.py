from typing import Any, Dict, Optional
import asyncio
import json
import logging
import time
from Domain.prompts import SOAP_DRAFT_SYSTEM, build_soap_draft_prompt
from Domain.interfaces import ILLMClient, IClinicalClient, IEmrResultClient

logger = logging.getLogger(__name__)

# Keep endpoint latency below gateway timeout so failures are explicit and actionable.
SOAP_DRAFT_TIMEOUT_S = 50


class SoapDraftUseCase:
    """
    Tier 2: Generate a structured SOAP note draft from patient history and labs.
    Synchronous (returns full JSON).
    """

    def __init__(self, llm: ILLMClient, clinical: IClinicalClient,
                 emr_result: IEmrResultClient):
        self._llm        = llm
        self._clinical   = clinical
        self._emr_result = emr_result

    async def execute(
        self,
        patient_id:  str,
        token:       str,
        x_user_id:   str,
        x_user_role: str,
        triage_session_id: Optional[str] = None
    ) -> Dict[str, str]:
        started = time.perf_counter()

        # 1. Fetch patient context (diagnoses, meds, etc.)
        context = await self._clinical.get_patient_context(
            patient_id, x_user_id, x_user_role
        )
        logger.info("SOAP draft context fetched in %.2fs", time.perf_counter() - started)

        # 2. Fetch recent labs
        recent_labs = await self._emr_result.get_recent_results(
            patient_id, token, x_user_id, x_user_role, limit=5
        )
        logger.info("SOAP draft labs fetched in %.2fs", time.perf_counter() - started)

        # 3. Fetch triage summary if session_id provided
        triage_summary = None
        # Note: If we had an IAIInternalClient we could fetch triage sessions here
        # For now we'll assume the caller might pass the summary or we'll skip it

        user_prompt = build_soap_draft_prompt(
            context, recent_labs, triage_summary=triage_summary
        )

        try:
            raw = await asyncio.wait_for(
                self._llm.complete(
                    system_prompt=SOAP_DRAFT_SYSTEM,
                    user_prompt=user_prompt,
                    temperature=0.2,
                    json_mode=True,
                ),
                timeout=SOAP_DRAFT_TIMEOUT_S,
            )
        except asyncio.TimeoutError as exc:
            elapsed = time.perf_counter() - started
            logger.warning(
                "SOAP draft timed out after %.2fs (limit=%ss)",
                elapsed,
                SOAP_DRAFT_TIMEOUT_S,
            )
            raise TimeoutError("SOAP draft generation timed out") from exc

        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("SOAP draft JSON parse failed, returning raw: %s", exc)
            result = {"s": raw, "o": "", "a": "", "p": ""}

        logger.info("SOAP draft completed in %.2fs", time.perf_counter() - started)

        return result
