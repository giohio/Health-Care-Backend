import json
import logging
import re
from typing import Optional

from Domain.prompts import LAB_SUGGESTION_SYSTEM, build_lab_suggestion_prompt, _build_context_block
from Domain.interfaces import ILLMClient, IClinicalClient

logger = logging.getLogger(__name__)

# Default if Groq returns malformed JSON
_EMPTY_SUGGESTIONS: dict = {"suggestions": []}


def _extract_json(raw: str) -> str:
    """Strip markdown fences and extract the first complete JSON object."""
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    # Find first '{' and last '}' to handle surrounding prose
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


class LabSuggestionUseCase:
    """Non-streaming use case: suggest lab tests based on symptoms.

    Calls the LLM in JSON mode — returns a structured dict, never streams.
    Falls back to an empty list on parse errors so the route always returns 200.
    """

    def __init__(self, llm: ILLMClient, clinical: IClinicalClient) -> None:
        self._llm = llm
        self._clinical = clinical

    async def execute(
        self,
        symptoms: str,
        x_user_id: str,
        x_user_role: str,
        patient_id: Optional[str] = None,
        department: Optional[str] = None,
    ) -> dict:
        # Build patient context block (falls back gracefully if unavailable)
        patient_context = ""
        if patient_id:
            ctx = await self._clinical.get_patient_context(
                patient_id, x_user_id, x_user_role
            )
            patient_context = _build_context_block(ctx)

        user_prompt = build_lab_suggestion_prompt(
            symptoms=symptoms,
            department=department,
            patient_context=patient_context,
        )

        raw = await self._llm.complete(
            system_prompt=LAB_SUGGESTION_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=2048,
            json_mode=True,
        )

        try:
            result = json.loads(_extract_json(raw))
            if "suggestions" not in result:
                raise ValueError("missing 'suggestions' key")
            return result
        except ValueError as exc:
            logger.warning("LabSuggestionUseCase: failed to parse LLM JSON (%s)", exc)
            return _EMPTY_SUGGESTIONS

