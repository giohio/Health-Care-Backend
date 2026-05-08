import pytest
from pathlib import Path
from Rag.knowledge_base.pipeline.metadata import (
    VALID_DEPARTMENTS,
    _DISEASE_MAP,
    infer_disease_category,
    build_payload,
    ChunkPayload,
)


class TestValidDepartments:
    def test_contains_all_nine_ai_service_departments(self):
        required = {
            "respiratory", "dermatology", "neurology", "ophthalmology",
            "cardiology", "nephrology", "hematology", "endocrinology",
            "internal_medicine",
        }
        assert required.issubset(VALID_DEPARTMENTS)

    def test_contains_radiology_for_xray_knowledge(self):
        assert "radiology" in VALID_DEPARTMENTS

    def test_radiology_count_is_ten(self):
        assert len(VALID_DEPARTMENTS) == 10


class TestDiseaseCategoryInference:
    @pytest.mark.parametrize("text,page_title,expected", [
        ("The patient has pneumonia with consolidation in the right lower lobe",
         "Pneumonia", "pneumonia"),
        ("Chronic obstructive pulmonary disease with emphysema",
         "COPD Overview", "copd"),
        ("Melanoma with ABCDE features: asymmetry, border irregularity",
         "Melanoma", "melanoma"),
        ("Chronic kidney disease with eGFR stage 3 and elevated creatinine",
         "CKD", "ckd"),
        ("Type 2 diabetes with HbA1c of 8.5%",
         "Diabetes Type 2", "diabetes"),
        ("Complete blood count shows low hemoglobin and low MCV",
         "CBC Interpretation", "cbc_interpretation"),
        ("ECG shows atrial fibrillation with irregular rhythm",
         "Arrhythmia Overview", "ecg_arrhythmia"),
        ("Transverse bone fracture of the tibia confirmed on imaging",
         "Bone Fracture Report", "bone_fracture"),
        ("Cervical spine X-ray shows spondylosis with disc degeneration and osteophyte spine formation",
         "Spine X-ray", "degenerative_spine"),
        ("Bowel gas pattern shows dilated bowel loops consistent with small bowel obstruction",
         "Abdominal X-ray", "bowel_obstruction"),
        ("Glioma in the temporal lobe with contrast enhancement",
         "Glioma", "brain_tumor"),
    ])
    def test_infer_disease_category_returns_expected(self, text, page_title, expected):
        result = infer_disease_category(text, page_title)
        assert result == expected

    def test_infer_disease_category_unknown_returns_general(self):
        result = infer_disease_category(
            "Patient presenting for routine checkup",
            "General Checkup"
        )
        assert result == "general"

    def test_infer_disease_category_case_insensitive(self):
        result = infer_disease_category(
            "HEMOGLOBIN LOW CBC ABNORMAL",
            "Blood Test"
        )
        assert result == "cbc_interpretation"


class TestBuildPayload:
    def test_radiology_department_accepted(self):
        payload = build_payload(
            chunk_text="Chest X-ray shows normal cardiac silhouette.",
            chunk_type="parent",
            parent_id=None,
            source_type="radiopaedia",
            department="radiology",
            filepath=Path("rag_knowledge_base/clinical/radiology/dept_overview.md"),
            markdown_text="# Radiology Overview\n\nContent here.",
        )
        assert payload.department == "radiology"

    def test_unknown_department_falls_back_to_internal_medicine(self):
        payload = build_payload(
            chunk_text="Some clinical content.",
            chunk_type="parent",
            parent_id=None,
            source_type="clinical",
            department="unknown_specialty",
            filepath=Path("rag_knowledge_base/clinical/misc/doc.md"),
            markdown_text="# Document",
        )
        assert payload.department == "internal_medicine"

    def test_payload_contains_required_fields(self):
        payload = build_payload(
            chunk_text="This is a bone fracture X-ray report describing the fracture line.",
            chunk_type="parent",
            parent_id=None,
            source_type="radiopaedia",
            department="radiology",
            filepath=Path("rag_knowledge_base/clinical/radiology/fracture.md"),
            markdown_text="# Fracture Classification\n\nContent.",
        )
        assert payload.department == "radiology"
        assert payload.disease_category == "bone_fracture"
        assert payload.source == "radiopaedia"
        assert payload.chunk_type == "parent"
        assert payload.parent_id is None
        assert "bone fracture" in payload.text
        assert payload.char_count == len("This is a bone fracture X-ray report describing the fracture line.")
        assert payload.token_estimate == payload.char_count // 4

    def test_payload_to_dict_serialization(self):
        payload = build_payload(
            chunk_text="Test text.",
            chunk_type="fixed",
            parent_id=None,
            source_type="test",
            department="radiology",
            filepath=Path("test.md"),
            markdown_text="# Test",
        )
        d = payload.to_dict()
        assert isinstance(d, dict)
        assert d["department"] == "radiology"
        assert d["text"] == "Test text."

    def test_payload_parent_id_passed_through(self):
        payload = build_payload(
            chunk_text="Child chunk text.",
            chunk_type="child",
            parent_id="parent-uuid-123",
            source_type="test",
            department="radiology",
            filepath=Path("test.md"),
            markdown_text="# Test",
        )
        assert payload.parent_id == "parent-uuid-123"
        assert payload.chunk_type == "child"
