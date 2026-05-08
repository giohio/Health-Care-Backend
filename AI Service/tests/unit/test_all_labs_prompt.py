"""
Unit tests for Domain/prompts/_lab.py — ALL_LABS_SYNTHESIS_SYSTEM + build_all_labs_prompt
"""
import pytest
from Domain.entities import PatientContext
from Domain.prompts import ALL_LABS_SYNTHESIS_SYSTEM, build_all_labs_prompt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ctx(**kwargs) -> PatientContext:
    defaults = dict(
        patient_id="p-001",
        full_name="Nguyễn Văn A",
        age=45,
        gender="male",
        active_diagnoses=["Hypertension", "Type 2 Diabetes"],
        current_medications=["Amlodipine 5mg", "Metformin 500mg"],
        allergies="Penicillin",
        chronic_conditions="Diabetes type 2",
    )
    defaults.update(kwargs)
    return PatientContext(**defaults)


_RESULTS = [
    {
        "test_name": "CBC",
        "ai_draft_text": "WBC elevated at 11.2",
        "published_text": "Leukocytosis confirmed.",
        "ai_visual_findings": None,
    },
    {
        "test_name": "Chest X-Ray",
        "ai_draft_text": None,
        "published_text": "RLL consolidation.",
        "ai_visual_findings": '{"impression": "consolidation"}',
    },
]


# ---------------------------------------------------------------------------
# ALL_LABS_SYNTHESIS_SYSTEM
# ---------------------------------------------------------------------------

def test_system_prompt_is_string():
    assert isinstance(ALL_LABS_SYNTHESIS_SYSTEM, str)
    assert len(ALL_LABS_SYNTHESIS_SYSTEM) > 100


def test_system_prompt_contains_holistic_keyword():
    lower = ALL_LABS_SYNTHESIS_SYSTEM.lower()
    assert "holistic" in lower or "cross" in lower


def test_system_prompt_requires_physician_review():
    assert "PHYSICIAN" in ALL_LABS_SYNTHESIS_SYSTEM or "physician" in ALL_LABS_SYNTHESIS_SYSTEM.lower()


def test_system_prompt_has_disclaimer():
    assert "DRAFT" in ALL_LABS_SYNTHESIS_SYSTEM


def test_system_prompt_has_priority_level_section():
    assert "Priority Level" in ALL_LABS_SYNTHESIS_SYSTEM


# ---------------------------------------------------------------------------
# build_all_labs_prompt
# ---------------------------------------------------------------------------

def test_returns_string():
    ctx = _ctx()
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert isinstance(result, str)
    assert len(result) > 50


def test_includes_patient_name():
    ctx = _ctx(full_name="Trần Thị B")
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert "Trần Thị B" in result


def test_includes_patient_age():
    ctx = _ctx(age=55)
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert "55" in result


def test_includes_all_test_names():
    ctx = _ctx()
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert "CBC" in result
    assert "Chest X-Ray" in result


def test_uses_published_text_over_draft():
    """published_text should take priority over ai_draft_text."""
    ctx = _ctx()
    single = [{"test_name": "CBC", "published_text": "PUBLISHED_VALUE", "ai_draft_text": "DRAFT_VALUE", "ai_visual_findings": None}]
    result = build_all_labs_prompt(single, ctx)
    assert "PUBLISHED_VALUE" in result
    # draft value should not appear when published_text is set
    assert "DRAFT_VALUE" not in result


def test_falls_back_to_draft_when_no_published_text():
    ctx = _ctx()
    single = [{"test_name": "CBC", "published_text": None, "ai_draft_text": "DRAFT_FALLBACK", "ai_visual_findings": None}]
    result = build_all_labs_prompt(single, ctx)
    assert "DRAFT_FALLBACK" in result


def test_includes_visual_findings_when_present():
    ctx = _ctx()
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert "consolidation" in result


def test_empty_results_returns_string():
    """Should not crash with an empty results list."""
    ctx = _ctx()
    result = build_all_labs_prompt([], ctx)
    assert isinstance(result, str)


def test_active_diagnoses_included():
    ctx = _ctx(active_diagnoses=["UNIQUE_DIAGNOSIS_MARKER"])
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert "UNIQUE_DIAGNOSIS_MARKER" in result


def test_current_medications_included():
    ctx = _ctx(current_medications=["SPECIAL_DRUG_MARKER"])
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert "SPECIAL_DRUG_MARKER" in result


def test_allergies_included():
    ctx = _ctx(allergies="PENICILLIN_MARKER")
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert "PENICILLIN_MARKER" in result


def test_patient_gender_included():
    ctx = _ctx(gender="female")
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert "female" in result


def test_none_age_handled_gracefully():
    ctx = _ctx(age=None)
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert isinstance(result, str)
    assert "N/A" in result


def test_empty_diagnoses_handled():
    ctx = _ctx(active_diagnoses=[])
    result = build_all_labs_prompt(_RESULTS, ctx)
    assert isinstance(result, str)
    assert "None" in result  # fallback label


def test_english_instruction_in_prompt():
    ctx = _ctx()
    result = build_all_labs_prompt(_RESULTS, ctx)
    lower = result.lower()
    assert "english" in lower


def test_multiple_tests_all_numbered():
    """Each test should appear with an index separator."""
    ctx = _ctx()
    result = build_all_labs_prompt(_RESULTS, ctx)
    # Both test separators should be present
    assert "[1]" in result
    assert "[2]" in result
