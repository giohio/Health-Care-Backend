import pytest
from Domain.prompts import (
    SYMPTOM_CHECK_SYSTEM,
    TRIAGE_SYSTEM_PROMPT,
    VISION_PROMPTS,
    LAB_SYNTHESIS_SYSTEM,
    EMR_SUMMARY_SYSTEM,
    AI_DISCLAIMER_VI,
    build_symptom_check_prompt,
    build_triage_messages,
    build_lab_synthesis_prompt,
    build_emr_summary_prompt,
)
from Domain.entities import ConversationTurn, PatientContext, SymptomCheckRequest


def test_symptom_check_system_forbids_diagnosis():
    # New prompt uses "Không chẩn đoán bệnh cụ thể" in TUYỆT ĐỐI KHÔNG section
    assert "Không chẩn đoán bệnh cụ thể" in TRIAGE_SYSTEM_PROMPT


def test_symptom_check_system_alias_equals_triage_prompt():
    assert SYMPTOM_CHECK_SYSTEM is TRIAGE_SYSTEM_PROMPT


def test_symptom_check_system_requests_vietnamese():
    assert "tiếng Việt" in SYMPTOM_CHECK_SYSTEM


def test_symptom_check_system_has_q_r_markers():
    assert "[Q]" in TRIAGE_SYSTEM_PROMPT
    assert "[R]" in TRIAGE_SYSTEM_PROMPT


def test_vision_prompts_has_all_required_keys():
    expected = {
        "chest_xray", "ecg", "skin_lesion", "brain_mri", "fundus",
        "blood_panel", "bone_xray", "abdominal_xray", "skull_xray", "spine_xray",
    }
    assert set(VISION_PROMPTS.keys()) == expected


def test_vision_prompts_all_request_json_output():
    for key, prompt in VISION_PROMPTS.items():
        assert "JSON" in prompt, f"Vision prompt '{key}' missing JSON instruction"


def test_lab_synthesis_system_starts_with_draft_warning():
    assert "BẢN NHÁP" in LAB_SYNTHESIS_SYSTEM


def test_emr_summary_system_has_structure():
    assert "Patient Information" in EMR_SUMMARY_SYSTEM


def test_ai_disclaimer_vi_is_non_empty():
    assert len(AI_DISCLAIMER_VI) > 30


# ─── build_triage_messages ────────────────────────────────────────────────────

def test_build_triage_messages_first_turn_structure():
    context = PatientContext(
        patient_id="p-1",
        full_name="Trần Thị B",
        age=30,
        gender="female",
        active_diagnoses=["Hen phế quản"],
        current_medications=[],
        allergies="",
        chronic_conditions="",
    )
    request = SymptomCheckRequest(patient_id="p-1", symptoms="Đau ngực dữ dội")

    msgs = build_triage_messages(request, context)

    # System message contains patient context
    assert msgs[0]["role"] == "system"
    system_content = msgs[0]["content"]
    assert "Trần Thị B" in system_content
    assert "30" in system_content
    assert "Hen phế quản" in system_content

    # Last message is the user turn
    assert msgs[-1]["role"] == "user"
    assert "Đau ngực dữ dội" in msgs[-1]["content"]


def test_build_triage_messages_includes_duration_and_severity():
    context = PatientContext(
        patient_id="p-2", full_name="Bệnh nhân", age=None, gender=None
    )
    request = SymptomCheckRequest(
        patient_id="p-2",
        symptoms="Ho kéo dài",
        duration="2 tuần",
        severity="nhẹ",
    )

    msgs = build_triage_messages(request, context)
    user_content = msgs[-1]["content"]

    assert "2 tuần" in user_content
    assert "nhẹ" in user_content


def test_build_triage_messages_with_history():
    context = PatientContext(patient_id="p-3", full_name="Test", age=None, gender=None)
    history = [
        ConversationTurn(role="patient",   content="Tôi bị đau đầu"),
        ConversationTurn(role="assistant", content="[Q] Đau ở vị trí nào?"),
    ]
    request = SymptomCheckRequest(
        patient_id="p-3",
        symptoms="Đau ở thái dương",
        conversation_history=history,
    )

    msgs = build_triage_messages(request, context)

    # system + patient turn + assistant turn + current patient turn = 4
    assert len(msgs) == 4
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Tôi bị đau đầu"
    assert msgs[2]["role"] == "assistant"
    assert msgs[2]["content"] == "[Q] Đau ở vị trí nào?"
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "Đau ở thái dương"


# ─── build_symptom_check_prompt shim ─────────────────────────────────────────

def test_build_symptom_check_prompt_shim_returns_user_content():
    context = PatientContext(patient_id="p-4", full_name="N/A", age=None, gender=None)
    request = SymptomCheckRequest(
        patient_id="p-4",
        symptoms="Ho kéo dài",
        duration="2 tuần",
        severity="nhẹ",
    )

    prompt = build_symptom_check_prompt(request, context)

    assert "2 tuần" in prompt
    assert "nhẹ" in prompt


def test_build_symptom_check_prompt_includes_medications_and_allergies():
    """Medications and allergies appear in the system message (index 0) of the triage messages."""
    context = PatientContext(
        patient_id="p-3",
        full_name="Lê Văn C",
        age=60,
        gender="male",
        active_diagnoses=[],
        current_medications=["Metformin 500mg", "Amlodipine 5mg"],
        allergies="Penicillin",
        chronic_conditions="",
    )
    request = SymptomCheckRequest(patient_id="p-3", symptoms="Mệt mỏi kéo dài")

    msgs = build_triage_messages(request, context)
    system_content = msgs[0]["content"]

    assert "Metformin 500mg" in system_content
    assert "Penicillin" in system_content


def test_build_lab_synthesis_prompt_includes_test_name(patient_context):
    findings = {"panel_type": "cbc", "confidence": 0.9}
    prompt   = build_lab_synthesis_prompt(findings, patient_context, "CBC máu toàn phần")

    assert "CBC máu toàn phần" in prompt
    assert patient_context.full_name in prompt


def test_build_emr_summary_prompt_with_no_labs(patient_context):
    prompt = build_emr_summary_prompt(patient_context, [])

    assert patient_context.full_name in prompt
    assert "Không có" in prompt


def test_build_emr_summary_prompt_with_labs(patient_context):
    labs   = [{"test_name": "X-quang ngực", "summary": "Bình thường"}]
    prompt = build_emr_summary_prompt(patient_context, labs)

    assert "X-quang ngực" in prompt
