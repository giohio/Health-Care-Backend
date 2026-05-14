"""
Unit tests for new prompts in Domain/prompts.py:
  - _rag_block
  - build_lab_chat_messages (patient + doctor)
  - build_clinical_assist_messages
  - AUSCULTATION_VISION_PROMPTS, AUSCULTATION_SYNTHESIS_SYSTEM
  - build_auscultation_synthesis_prompt
  - Updated build_triage_messages, build_lab_synthesis_prompt, build_emr_summary_prompt
    (rag_context parameter added to each)
"""

import pytest
from Domain.entities import PatientContext
from Domain.prompts import (
    _rag_block,
    build_triage_messages,
    build_lab_synthesis_prompt,
    build_emr_summary_prompt,
    build_lab_chat_messages,
    build_clinical_assist_messages,
    AUSCULTATION_VISION_PROMPTS,
    AUSCULTATION_SYNTHESIS_SYSTEM,
    build_auscultation_synthesis_prompt,
    LAB_CHAT_SYSTEM_PATIENT,
    LAB_CHAT_SYSTEM_DOCTOR,
    CLINICAL_ASSIST_SYSTEM,
)
from Domain.entities import SymptomCheckRequest


# ---------------------------------------------------------------------------
# _rag_block
# ---------------------------------------------------------------------------

def test_rag_block_returns_empty_string_when_context_is_empty():
    assert _rag_block("") == ""


def test_rag_block_returns_empty_string_when_context_is_none_like_falsy():
    assert _rag_block(None) == ""  # type: ignore[arg-type]


def test_rag_block_wraps_non_empty_context():
    result = _rag_block("Some guideline text")
    assert "Some guideline text" in result
    # Must wrap with something to visually separate from the base prompt
    assert result.startswith("\n") or result.endswith("\n")


def test_rag_block_does_not_corrupt_context_text():
    ctx = "── KNOWLEDGE BASE CONTEXT ──\nDiabetes guidelines\n── END CONTEXT ──"
    result = _rag_block(ctx)
    assert ctx in result


# ---------------------------------------------------------------------------
# build_triage_messages — rag_context parameter
# ---------------------------------------------------------------------------

def _patient_context(diagnoses=None):
    return PatientContext(
        patient_id="p-triage",
        full_name="Nguyễn Văn X",
        age=30,
        gender="male",
        active_diagnoses=diagnoses or [],
    )


def _symptom_request(symptoms="Đau đầu"):
    return SymptomCheckRequest(patient_id="p-triage", symptoms=symptoms)


def test_build_triage_messages_no_rag_does_not_contain_context_marker():
    msgs = build_triage_messages(_symptom_request(), _patient_context(), rag_context="")
    system = msgs[0]["content"]
    assert "KNOWLEDGE BASE CONTEXT" not in system


def test_build_triage_messages_injects_rag_context():
    ctx = "── KNOWLEDGE BASE CONTEXT ──\nHeadache guidelines\n── END CONTEXT ──"
    msgs = build_triage_messages(_symptom_request(), _patient_context(), rag_context=ctx)
    system = msgs[0]["content"]
    assert "Headache guidelines" in system


def test_build_triage_messages_user_content_is_symptoms():
    msgs = build_triage_messages(
        _symptom_request(symptoms="Ho khan kéo dài"),
        _patient_context(),
    )
    user_msg = msgs[-1]["content"]
    assert "Ho khan kéo dài" in user_msg


# ---------------------------------------------------------------------------
# build_lab_synthesis_prompt — rag_context parameter
# ---------------------------------------------------------------------------

def _ctx():
    return PatientContext(
        patient_id="p-lab",
        full_name="Trần Thị Y",
        age=45,
        gender="female",
    )


def test_build_lab_synthesis_no_rag_does_not_contain_context_marker():
    result = build_lab_synthesis_prompt({"HbA1c": "9.2%"}, _ctx(), "Metabolic Panel", rag_context="")
    assert "KNOWLEDGE BASE CONTEXT" not in result


def test_build_lab_synthesis_injects_rag_context():
    ctx = "── KNOWLEDGE BASE CONTEXT ──\nADA 2024 HbA1c targets\n── END CONTEXT ──"
    result = build_lab_synthesis_prompt({"HbA1c": "9.2%"}, _ctx(), "Metabolic Panel", rag_context=ctx)
    assert "ADA 2024 HbA1c targets" in result


def test_build_lab_synthesis_contains_patient_name():
    result = build_lab_synthesis_prompt({}, _ctx(), "CBC")
    assert "Trần Thị Y" in result


# ---------------------------------------------------------------------------
# build_emr_summary_prompt — rag_context parameter
# ---------------------------------------------------------------------------

def test_build_emr_summary_no_rag_does_not_contain_context_marker():
    result = build_emr_summary_prompt(_ctx(), [], rag_context="")
    assert "KNOWLEDGE BASE CONTEXT" not in result


def test_build_emr_summary_injects_rag_context():
    ctx = "── KNOWLEDGE BASE CONTEXT ──\nHypertension management\n── END CONTEXT ──"
    result = build_emr_summary_prompt(_ctx(), [], rag_context=ctx)
    assert "Hypertension management" in result


# ---------------------------------------------------------------------------
# LAB_CHAT_SYSTEM_PATIENT — content guards
# ---------------------------------------------------------------------------

def test_lab_chat_patient_system_forbids_diagnosis():
    assert "diagnose" in LAB_CHAT_SYSTEM_PATIENT.lower()


def test_lab_chat_patient_system_encourages_consulting_doctor():
    # The patient system must contain a directive to see a doctor
    lowered = LAB_CHAT_SYSTEM_PATIENT.lower()
    assert "bác sĩ" in lowered or "physician" in lowered or "doctor" in lowered


def test_lab_chat_patient_system_requests_plain_language():
    lowered = LAB_CHAT_SYSTEM_PATIENT.lower()
    assert "đơn giản" in lowered or "plain" in lowered or "bệnh nhân" in lowered


# ---------------------------------------------------------------------------
# LAB_CHAT_SYSTEM_DOCTOR — content guards
# ---------------------------------------------------------------------------

def test_lab_chat_doctor_system_references_guidelines():
    lowered = LAB_CHAT_SYSTEM_DOCTOR.lower()
    assert "guideline" in lowered or "protocol" in lowered or "clinical" in lowered


def test_lab_chat_doctor_system_starts_with_ai_clinical_support():
    assert "AI CLINICAL SUPPORT" in LAB_CHAT_SYSTEM_DOCTOR


def test_lab_chat_doctor_system_mentions_critical_values():
    lowered = LAB_CHAT_SYSTEM_DOCTOR.lower()
    assert "critical" in lowered or "urgent" in lowered or "immediate" in lowered


# ---------------------------------------------------------------------------
# build_lab_chat_messages — structure
# ---------------------------------------------------------------------------

def test_build_lab_chat_messages_patient_role_uses_patient_system():
    msgs = build_lab_chat_messages("What is HbA1c?", "patient")
    assert msgs[0]["role"] == "system"
    # Patient system contains Vietnamese text
    assert "bệnh nhân" in msgs[0]["content"].lower() or "patient" in msgs[0]["content"].lower()


def test_build_lab_chat_messages_doctor_role_uses_doctor_system():
    msgs = build_lab_chat_messages("Interpret HbA1c 9%", "doctor")
    assert "AI CLINICAL SUPPORT" in msgs[0]["content"]


def test_build_lab_chat_messages_user_content_is_question():
    question = "Is my WBC count normal?"
    msgs = build_lab_chat_messages(question, "doctor")
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == question


def test_build_lab_chat_messages_patient_context_block_in_system():
    patient_block = "──── THÔNG TIN BỆNH NHÂN ────\nHọ tên : Lê Văn C\n────"
    msgs = build_lab_chat_messages(
        "What is HbA1c?", "patient", patient_context_block=patient_block
    )
    assert "Lê Văn C" in msgs[0]["content"]


def test_build_lab_chat_messages_rag_context_in_system():
    rag = "── KNOWLEDGE BASE CONTEXT ──\nHbA1c reference range\n── END CONTEXT ──"
    msgs = build_lab_chat_messages("HbA1c question", "doctor", rag_context=rag)
    assert "HbA1c reference range" in msgs[0]["content"]


def test_build_lab_chat_messages_no_rag_no_context_marker():
    msgs = build_lab_chat_messages("Simple question", "patient")
    assert "KNOWLEDGE BASE CONTEXT" not in msgs[0]["content"]


def test_build_lab_chat_messages_returns_two_messages():
    msgs = build_lab_chat_messages("Question", "patient")
    assert len(msgs) == 2


# ---------------------------------------------------------------------------
# CLINICAL_ASSIST_SYSTEM — content guards
# ---------------------------------------------------------------------------

def test_clinical_assist_system_requires_physician_judgment():
    assert "Physician judgment" in CLINICAL_ASSIST_SYSTEM or \
           "physician" in CLINICAL_ASSIST_SYSTEM.lower()


def test_clinical_assist_system_requires_guideline_citation():
    lowered = CLINICAL_ASSIST_SYSTEM.lower()
    assert "guideline" in lowered or "cite" in lowered or "protocol" in lowered


def test_clinical_assist_system_mentions_differential_diagnosis():
    lowered = CLINICAL_ASSIST_SYSTEM.lower()
    assert "differential" in lowered


# ---------------------------------------------------------------------------
# build_clinical_assist_messages — structure
# ---------------------------------------------------------------------------

def test_build_clinical_assist_messages_returns_two_messages():
    msgs = build_clinical_assist_messages("What is first-line for HTN?")
    assert len(msgs) == 2


def test_build_clinical_assist_messages_system_role_first():
    msgs = build_clinical_assist_messages("Question")
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_build_clinical_assist_messages_user_content():
    question = "Differential for elevated troponin?"
    msgs = build_clinical_assist_messages(question)
    assert msgs[1]["content"] == question


def test_build_clinical_assist_messages_rag_in_system():
    rag = "── KNOWLEDGE BASE CONTEXT ──\nACS guidelines\n── END CONTEXT ──"
    msgs = build_clinical_assist_messages("Troponin elevation", rag_context=rag)
    assert "ACS guidelines" in msgs[0]["content"]


def test_build_clinical_assist_messages_patient_block_in_system():
    block = "──── THÔNG TIN BỆNH NHÂN ────\nHọ tên : Phạm Văn D\n────"
    msgs = build_clinical_assist_messages("Review patient", patient_block=block)
    assert "Phạm Văn D" in msgs[0]["content"]


# ---------------------------------------------------------------------------
# AUSCULTATION_VISION_PROMPTS — structure
# ---------------------------------------------------------------------------

def test_auscultation_vision_prompts_has_lung_sounds_key():
    assert "lung_sounds" in AUSCULTATION_VISION_PROMPTS


def test_auscultation_vision_prompts_has_heart_sounds_key():
    assert "heart_sounds" in AUSCULTATION_VISION_PROMPTS


def test_lung_sounds_prompt_instructs_no_diagnosis():
    lowered = AUSCULTATION_VISION_PROMPTS["lung_sounds"].lower()
    assert "no" in lowered and "diagnos" in lowered or "do not diagnose" in lowered or \
           "not diagnose" in lowered


def test_heart_sounds_prompt_requests_json_response():
    prompt = AUSCULTATION_VISION_PROMPTS["heart_sounds"]
    assert "json" in prompt.lower() or "JSON" in prompt


# ---------------------------------------------------------------------------
# AUSCULTATION_SYNTHESIS_SYSTEM — content guards
# ---------------------------------------------------------------------------

def test_auscultation_synthesis_system_is_non_empty():
    assert len(AUSCULTATION_SYNTHESIS_SYSTEM) > 50


def test_auscultation_synthesis_system_mentions_physician():
    lowered = AUSCULTATION_SYNTHESIS_SYSTEM.lower()
    assert "physician" in lowered or "bác sĩ" in lowered


# ---------------------------------------------------------------------------
# build_auscultation_synthesis_prompt
# ---------------------------------------------------------------------------

def _findings():
    return {
        "findings": "Bilateral crackles at bases.",
        "keywords": ["crackles", "reduced"],
        "confidence": 0.80,
    }


def test_build_auscultation_synthesis_prompt_includes_sound_type():
    patient = PatientContext(patient_id="p-asc", full_name="Test", age=60, gender="male")
    result = build_auscultation_synthesis_prompt(_findings(), patient, "lung_sounds", language="vi")
    assert "lung_sounds" in result or "lung" in result.lower()


def test_build_auscultation_synthesis_prompt_includes_findings_text():
    patient = PatientContext(patient_id="p-asc", full_name="Test", age=60, gender="male")
    result = build_auscultation_synthesis_prompt(_findings(), patient, "lung_sounds", language="en")
    assert "Bilateral crackles" in result or "crackles" in result


def test_build_auscultation_synthesis_prompt_includes_patient_name():
    patient = PatientContext(patient_id="p-asc", full_name="Ngô Thị E", age=45, gender="female")
    result = build_auscultation_synthesis_prompt(_findings(), patient, "heart_sounds", language="vi")
    assert "Ngô Thị E" in result


def test_build_auscultation_synthesis_prompt_returns_string():
    patient = PatientContext(patient_id="p-asc", full_name="Test", age=50, gender="male")
    result = build_auscultation_synthesis_prompt(_findings(), patient, "lung_sounds")
    assert isinstance(result, str)
    assert len(result) > 20


# ---------------------------------------------------------------------------
# LAB_TABULAR_SYNTHESIS_SYSTEM
# ---------------------------------------------------------------------------
from Domain.prompts import LAB_TABULAR_SYNTHESIS_SYSTEM, build_lab_tabular_synthesis_prompt


def test_lab_tabular_synthesis_system_is_non_empty():
    assert isinstance(LAB_TABULAR_SYNTHESIS_SYSTEM, str)
    assert len(LAB_TABULAR_SYNTHESIS_SYSTEM) > 50


def test_lab_tabular_synthesis_system_begins_with_disclaimer():
    assert "AI DRAFT" in LAB_TABULAR_SYNTHESIS_SYSTEM


def test_lab_tabular_synthesis_system_explicitly_excludes_imaging():
    assert "imaging" in LAB_TABULAR_SYNTHESIS_SYSTEM.lower() or \
           "radiology" in LAB_TABULAR_SYNTHESIS_SYSTEM.lower()


def test_lab_tabular_synthesis_system_has_no_oncology_rules():
    # Oncology rules belong to the imaging path only
    assert "ONCOLOGY" not in LAB_TABULAR_SYNTHESIS_SYSTEM
    assert "mass_present" not in LAB_TABULAR_SYNTHESIS_SYSTEM


def test_lab_tabular_synthesis_system_escalates_diagnostic_glucose_abnormalities():
    lower = LAB_TABULAR_SYNTHESIS_SYSTEM.lower()
    assert "fasting glucose >= 7.0 mmol/l" in lower
    assert "hba1c >= 6.5%" in lower
    assert "must be at least priority" in lower
    assert "do not label the draft routine/low" in lower


def test_lab_tabular_synthesis_system_covers_common_lab_panels():
    lower = LAB_TABULAR_SYNTHESIS_SYSTEM.lower()
    for marker in [
        "cbc examples",
        "liver examples",
        "lipid examples",
        "thyroid examples",
        "urinalysis examples",
        "coagulation examples",
        "must be at least priority",
    ]:
        assert marker in lower


# ---------------------------------------------------------------------------
# build_lab_tabular_synthesis_prompt
# ---------------------------------------------------------------------------

def _tabular_ctx():
    return PatientContext(
        patient_id="p-cbc",
        full_name="Nguyễn Văn A",
        age=35,
        gender="male",
        recent_notes=["Patient has spiculated mass in right upper lobe, hilar lymphadenopathy noted"],
    )


def test_build_lab_tabular_prompt_contains_patient_demographics():
    result = build_lab_tabular_synthesis_prompt({"WBC": "11.5"}, _tabular_ctx(), "CBC")
    assert "35" in result   # age
    assert "male" in result


def test_build_lab_tabular_prompt_contains_test_name():
    result = build_lab_tabular_synthesis_prompt({"WBC": "11.5"}, _tabular_ctx(), "CBC")
    assert "CBC" in result


def test_build_lab_tabular_prompt_contains_findings():
    result = build_lab_tabular_synthesis_prompt({"WBC": "11.5"}, _tabular_ctx(), "CBC")
    assert "WBC" in result


def test_build_lab_tabular_prompt_does_not_include_recent_notes():
    """Key invariant: tabular prompt must NOT inject imaging/clinical note text."""
    result = build_lab_tabular_synthesis_prompt({"WBC": "11.5"}, _tabular_ctx(), "CBC")
    assert "spiculated mass" not in result
    assert "hilar lymphadenopathy" not in result
    assert "recent_notes" not in result.lower()


def test_build_lab_tabular_prompt_no_rag_no_context_marker():
    result = build_lab_tabular_synthesis_prompt({}, _tabular_ctx(), "CBC", rag_context="")
    assert "KNOWLEDGE BASE CONTEXT" not in result


def test_build_lab_tabular_prompt_injects_rag_context():
    rag = "── KNOWLEDGE BASE CONTEXT ──\nWHO CBC reference ranges 2024\n── END CONTEXT ──"
    result = build_lab_tabular_synthesis_prompt({}, _tabular_ctx(), "CBC", rag_context=rag)
    assert "WHO CBC reference ranges 2024" in result


def test_build_lab_tabular_prompt_is_string():
    result = build_lab_tabular_synthesis_prompt({}, _tabular_ctx(), "CBC")
    assert isinstance(result, str)
    assert len(result) > 20
