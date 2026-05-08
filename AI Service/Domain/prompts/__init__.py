"""
Domain.prompts package
======================
All system prompts and prompt-builder functions for the AI Service.

Organised into sub-modules by tier/domain:
  _base            — shared language-detection utilities and _rag_block()
  _triage          — TIER 1 triage agent (VI + EN prompts, booking logic, builders)
  _vision          — TIER 2 vision LLM prompts (VISION_PROMPTS dict)
  _triage_summary  — TIER 5 triage summary for doctor review
  _lab             — lab synthesis, EMR summary, lab chat, clinical assist, lab suggestions
  _auscultation    — heart/lung auscultation prompts

All public names are re-exported here so existing code using
  from Domain.prompts import X
continues to work unchanged.
"""

# ── Shared utilities ──────────────────────────────────────────────────────────
from ._base import (
    _VI_CHARS,
    _detect_language,
    _lang_instruction,
    _rag_block,
)

# ── TIER 1 — Triage agent ─────────────────────────────────────────────────────
from ._triage import (
    TRIAGE_SYSTEM_PROMPT,
    TRIAGE_SYSTEM_PROMPT_EN,
    SYMPTOM_CHECK_SYSTEM,
    SPECIALTIES_SCHEMA,
    _SPECIALTIES_EXTRACTION_SYSTEM,
    SPECIALTIES_EXTRACTION_PROMPT,
    build_specialties_extraction_prompt,
    _build_context_block,
    _lang_lock_message,
    _rag_instructions_block,
    _BOOKING_INTENT_KEYWORDS,
    _BOOKING_MODE_OVERRIDE_VI,
    _BOOKING_MODE_OVERRIDE_EN,
    _EMERGENCY_MARKERS,
    _detect_booking_mode,
    build_triage_messages,
    build_symptom_check_prompt,
)

# ── TIER 2 — Vision LLM ───────────────────────────────────────────────────────
from ._vision import VISION_PROMPTS

# ── TIER 2 — Lab / EMR / Clinical ────────────────────────────────────────────
from ._lab import (
    LAB_SYNTHESIS_SYSTEM,
    build_lab_synthesis_prompt,
    LAB_TABULAR_SYNTHESIS_SYSTEM,
    build_lab_tabular_synthesis_prompt,
    EMR_SUMMARY_SYSTEM,
    build_emr_summary_prompt,
    AI_DISCLAIMER_VI,
    AI_DISCLAIMER_EN,
    LAB_CHAT_SYSTEM_PATIENT,
    LAB_CHAT_SYSTEM_DOCTOR,
    build_lab_chat_messages,
    CLINICAL_ASSIST_SYSTEM,
    build_clinical_assist_messages,
    LAB_SUGGESTION_SYSTEM,
    build_lab_suggestion_prompt,
    TREATMENT_PLAN_SYSTEM,
    build_treatment_plan_prompt,
    ALL_LABS_SYNTHESIS_SYSTEM,
    build_all_labs_prompt,
    SOAP_DRAFT_SYSTEM,
    build_soap_draft_prompt,
)

# ── TIER 5 — Triage summary ──────────────────────────────────────────────────
from ._triage_summary import (
    TRIAGE_SUMMARY_SCHEMA,
    TRIAGE_SUMMARY_SYSTEM_PROMPT,
    TRIAGE_SUMMARY_USER_TEMPLATE,
    build_triage_summary_prompt,
)

# ── Auscultation ──────────────────────────────────────────────────────────────
from ._auscultation import (
    AUSCULTATION_VISION_PROMPTS,
    AUSCULTATION_SYNTHESIS_SYSTEM,
    build_auscultation_synthesis_prompt,
)

# Merged lookup: covers both standard imaging keys and auscultation spectrogram keys
ALL_VISION_PROMPTS: dict = {**VISION_PROMPTS, **AUSCULTATION_VISION_PROMPTS}

__all__ = [
    # base
    "_VI_CHARS", "_detect_language", "_lang_instruction", "_rag_block",
    # triage
    "TRIAGE_SYSTEM_PROMPT", "TRIAGE_SYSTEM_PROMPT_EN", "SYMPTOM_CHECK_SYSTEM",
    "SPECIALTIES_SCHEMA", "_SPECIALTIES_EXTRACTION_SYSTEM", "SPECIALTIES_EXTRACTION_PROMPT",
    "build_specialties_extraction_prompt",
    "_build_context_block", "_lang_lock_message", "_rag_instructions_block",
    "_BOOKING_INTENT_KEYWORDS", "_BOOKING_MODE_OVERRIDE_VI", "_BOOKING_MODE_OVERRIDE_EN",
    "_EMERGENCY_MARKERS", "_detect_booking_mode",
    "build_triage_messages", "build_symptom_check_prompt",
    # vision
    "VISION_PROMPTS",
    # lab
    "LAB_SYNTHESIS_SYSTEM", "build_lab_synthesis_prompt",
    "LAB_TABULAR_SYNTHESIS_SYSTEM", "build_lab_tabular_synthesis_prompt",
    "EMR_SUMMARY_SYSTEM", "build_emr_summary_prompt",
    "AI_DISCLAIMER_VI", "AI_DISCLAIMER_EN",
    "LAB_CHAT_SYSTEM_PATIENT", "LAB_CHAT_SYSTEM_DOCTOR", "build_lab_chat_messages",
    "CLINICAL_ASSIST_SYSTEM", "build_clinical_assist_messages",
    "LAB_SUGGESTION_SYSTEM", "build_lab_suggestion_prompt",
    "TREATMENT_PLAN_SYSTEM", "build_treatment_plan_prompt",
    "ALL_LABS_SYNTHESIS_SYSTEM", "build_all_labs_prompt",
    "SOAP_DRAFT_SYSTEM", "build_soap_draft_prompt",
    # triage summary
    "TRIAGE_SUMMARY_SCHEMA", "TRIAGE_SUMMARY_SYSTEM_PROMPT",
    "TRIAGE_SUMMARY_USER_TEMPLATE", "build_triage_summary_prompt",
    # auscultation
    "AUSCULTATION_VISION_PROMPTS", "AUSCULTATION_SYNTHESIS_SYSTEM",
    "build_auscultation_synthesis_prompt",
    # merged vision lookup
    "ALL_VISION_PROMPTS",
]
