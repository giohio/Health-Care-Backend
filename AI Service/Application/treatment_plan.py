import json
import logging
import re
from typing import Optional

from Domain.prompts import TREATMENT_PLAN_SYSTEM, build_treatment_plan_prompt, _build_context_block
from Domain.interfaces import ILLMClient, IClinicalClient

logger = logging.getLogger(__name__)

_EMPTY_PLAN: dict = {
    "summary": "Unable to generate treatment plan at this time.",
    "urgency": "ROUTINE",
    "follow_up_days": None,
    "recommendations": [],
}


def _extract_json(raw: str) -> str:
    """Strip markdown fences and extract the first complete JSON object."""
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


class TreatmentPlanUseCase:
    """Non-streaming use case: generate a treatment plan from lab results + clinical context.

    Calls the LLM in JSON mode and returns a structured dict.
    Falls back to an empty plan on parse errors so the route always returns 200.
    """

    def __init__(self, llm: ILLMClient, clinical: IClinicalClient) -> None:
        self._llm = llm
        self._clinical = clinical

    async def execute(
        self,
        lab_summary: str,
        x_user_id: str,
        x_user_role: str,
        patient_id: Optional[str] = None,
        symptoms: Optional[str] = None,
    ) -> dict:
        patient_context = ""
        if patient_id:
            ctx = await self._clinical.get_patient_context(
                patient_id, x_user_id, x_user_role
            )
            patient_context = _build_context_block(ctx)

        user_prompt = build_treatment_plan_prompt(
            lab_summary=lab_summary,
            patient_context=patient_context,
            symptoms=symptoms,
        )

        raw = await self._llm.complete(
            system_prompt=TREATMENT_PLAN_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=2048,
            json_mode=True,
        )

        try:
            result = json.loads(_extract_json(raw))
            if "recommendations" not in result:
                raise ValueError("missing 'recommendations' key")
            return result
        except ValueError as exc:
            logger.warning("TreatmentPlanUseCase: failed to parse LLM JSON (%s)", exc)
            return _EMPTY_PLAN
