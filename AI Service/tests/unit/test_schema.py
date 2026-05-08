"""
Unit tests for presentation/schema.py

Validates Pydantic input schema models: required fields, validators,
and optional fields with defaults.
"""

import pytest
from pydantic import ValidationError

from presentation.schema import SymptomCheckInput, TriggerLabAnalysisInput, EmrSummaryInput


# ---------------------------------------------------------------------------
# SymptomCheckInput tests
# ---------------------------------------------------------------------------

def test_symptom_check_input_valid():
    data = SymptomCheckInput(
        patient_id="p-001",
        symptoms="Đau đầu kéo dài 3 ngày, kèm buồn nôn.",
    )
    assert data.patient_id == "p-001"
    assert data.duration   is None
    assert data.severity   is None
    assert data.session_id is None


def test_symptom_check_input_with_optional_fields():
    data = SymptomCheckInput(
        patient_id="p-002",
        symptoms="Ho khan và sốt nhẹ từ hôm qua.",
        duration="1 ngày",
        severity="nhẹ",
    )
    assert data.duration == "1 ngày"
    assert data.severity == "nhẹ"


def test_symptom_check_input_with_session_id():
    data = SymptomCheckInput(
        patient_id="p-003",
        symptoms="Có",
        session_id="abc-123",
    )
    assert data.session_id == "abc-123"
    # Short follow-up answers (min_length=1) are valid
    assert data.symptoms == "Có"


def test_symptom_check_input_symptoms_empty():
    """Empty string fails min_length=1."""
    with pytest.raises(ValidationError):
        SymptomCheckInput(patient_id="p-001", symptoms="")


def test_symptom_check_input_symptoms_too_long():
    with pytest.raises(ValidationError):
        SymptomCheckInput(patient_id="p-001", symptoms="a" * 2001)


def test_symptom_check_input_missing_patient_id():
    with pytest.raises(ValidationError):
        SymptomCheckInput(symptoms="Đau đầu kéo dài liên tục.")


def test_symptom_check_input_missing_symptoms():
    with pytest.raises(ValidationError):
        SymptomCheckInput(patient_id="p-001")



# ---------------------------------------------------------------------------
# TriggerLabAnalysisInput tests
# ---------------------------------------------------------------------------

def test_trigger_lab_input_valid_image():
    data = TriggerLabAnalysisInput(
        result_id="r-001",
        patient_id="p-001",
        file_url="https://storage.example.com/xray.jpg",
        input_type="image",
        department="respiratory",
        test_name="Chest X-Ray",
        auth_token="internal-token",
    )
    assert data.tabular_data is None
    assert data.input_type == "image"


def test_trigger_lab_input_valid_tabular():
    data = TriggerLabAnalysisInput(
        result_id="r-002",
        patient_id="p-002",
        file_url="",
        input_type="tabular",
        department="hematology",
        test_name="CBC",
        tabular_data={"wbc": 7.5, "rbc": 4.2},
        auth_token="static-token",
    )
    assert data.tabular_data["wbc"] == pytest.approx(7.5)


def test_trigger_lab_input_missing_required_fields():
    with pytest.raises(ValidationError):
        TriggerLabAnalysisInput(
            result_id="r-001",
            # patient_id missing
            file_url="http://example.com/file",
            input_type="image",
            department="respiratory",
            test_name="X-Ray",
            auth_token="token",
        )


# ---------------------------------------------------------------------------
# EmrSummaryInput tests
# ---------------------------------------------------------------------------

def test_emr_summary_input_valid():
    data = EmrSummaryInput(patient_id="p-001")
    assert data.patient_id == "p-001"


def test_emr_summary_input_missing_patient_id():
    with pytest.raises(ValidationError):
        EmrSummaryInput()
