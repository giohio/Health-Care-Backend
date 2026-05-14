"""
Unit tests for the enhanced AI Triage Summary feature.

Tests the generate_summary() method and the enriched schema with:
- patient_description: verbatim quote from patient
- clinical_reasoning: why suspected conditions are inferred

Test cases:
1. Rich conversation → all fields including new ones are populated
2. Short conversation → missing reasoning is backfilled from conversation
3. Schema validation: TriageSummaryResponse accepts new fields
4. Doctor can call summary; patient gets TriageSessionAccessDenied
"""
import pytest

from Application.triage_session import (
    TriageSessionAccessDenied,
    TriageSessionService,
)
from Domain.entities import TriageSession
from Domain.enums import TriageSessionStatus


# ─────────────────────────────────────────────────────────────────────────────
#  Fake LLM client
# ─────────────────────────────────────────────────────────────────────────────

class FakeLLMClient:
    def __init__(self, response: dict | None):
        self.response = response
        self.call_count = 0

    async def complete_structured(self, **kwargs):
        self.call_count += 1
        return self.response


# ─────────────────────────────────────────────────────────────────────────────
#  Fake Repository (same as test_triage_session_service.py)
# ─────────────────────────────────────────────────────────────────────────────

from typing import Optional

from Domain.interfaces.triage_session_repository import ITriageSessionRepository


class FakeTriageSessionRepo(ITriageSessionRepository):
    def __init__(self):
        self._store: dict[str, TriageSession] = {}

    async def save(self, session: TriageSession) -> TriageSession:
        self._store[session.id] = session
        return session

    async def get_by_id(self, session_id: str) -> Optional[TriageSession]:
        return self._store.get(session_id)

    async def list_by_patient(self, patient_id: str) -> list[TriageSession]:
        return [s for s in self._store.values() if s.patient_id == patient_id]

    async def list_all(self, status_filter: Optional[str] = None) -> list[TriageSession]:
        sessions = list(self._store.values())
        if status_filter:
            sessions = [s for s in sessions if s.status.value == status_filter]
        return sessions


def _make_service():
    return TriageSessionService(FakeTriageSessionRepo())


# ─────────────────────────────────────────────────────────────────────────────
#  Test 1: Rich conversation → all fields including new ones are populated
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_summary_rich_conversation_returns_all_new_fields():
    svc = _make_service()
    fake_repo = svc._repo

    session = await svc.start_session("patient-1")

    await svc.finish_turn(
        session.id,
        patient_message="Tôi bị đau ngực trái, khó thở từ sáng nay, đổ mồ hôi nhiều",
        assistant_response="[R] Đây là trường hợp Cấp cứu — Tim mạch.",
        is_recommendation=True,
    )

    fake_llm = FakeLLMClient({
        "chief_complaint": "Acute left-sided chest pain with dyspnea and diaphoresis",
        "reported_symptoms": [
            "Left chest pain",
            "Shortness of breath since morning",
            "Profuse sweating",
        ],
        "duration": "Since this morning (approx. 4 hours)",
        "severity": "Severe",
        "suspected_conditions": [
            "Acute coronary syndrome (ACS)",
            "Pulmonary embolism",
        ],
        "department_reasoning": "Symptoms suggest a cardiac emergency requiring immediate Cardiology evaluation.",
        "recommended_department": "Cardiology",
        "urgency_level": "Emergency",
        "patient_description": "Tôi bị đau ngực trái, khó thở từ sáng nay, đổ mồ hôi nhiều",
        "clinical_reasoning": "Left-sided chest pain with diaphoresis is a classic presentation of acute coronary syndrome. "
                              "The acute dyspnea raises concern for either cardiac ischaemia or pulmonary embolism.",
    })

    result = await svc.generate_summary(
        session_id=session.id,
        requester_id="doctor-1",
        role="doctor",
        llm_client=fake_llm,
    )

    assert result["chief_complaint"] == "Acute left-sided chest pain with dyspnea and diaphoresis"
    assert result["patient_description"] == "Tôi bị đau ngực trái, khó thở từ sáng nay, đổ mồ hôi nhiều"
    assert result["clinical_reasoning"].startswith("Left-sided chest pain with diaphoresis")
    assert result["suspected_conditions"] == [
        "Acute coronary syndrome (ACS)",
        "Pulmonary embolism",
    ]
    assert result["urgency_level"] == "Emergency"
    assert fake_llm.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
#  Test 2: Short conversation → missing fields are backfilled
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_summary_short_conversation_backfills_empty_reasoning_fields():
    svc = _make_service()

    session = await svc.start_session("patient-1")
    await svc.finish_turn(
        session.id,
        patient_message="Đau đầu nhẹ",
        assistant_response="[R] Thần kinh. Thông thường.",
        is_recommendation=True,
    )

    fake_llm = FakeLLMClient({
        "chief_complaint": "Mild headache",
        "reported_symptoms": ["Headache"],
        "duration": "Unknown",
        "severity": "Mild",
        "suspected_conditions": ["Tension-type headache"],
        "department_reasoning": "Patient described a mild headache without red flags.",
        "recommended_department": "Neurology",
        "urgency_level": "Routine",
        # new fields intentionally absent or empty
        "patient_description": "",
        "clinical_reasoning": "",
    })

    result = await svc.generate_summary(
        session_id=session.id,
        requester_id="doctor-1",
        role="doctor",
        llm_client=fake_llm,
    )

    assert result["patient_description"] == "Đau đầu nhẹ"
    assert "primary headache syndrome" in result["clinical_reasoning"]
    assert result["chief_complaint"] == "Mild headache"


@pytest.mark.asyncio
async def test_generate_summary_llm_empty_uses_conversation_fallback():
    svc = _make_service()
    session = await svc.start_session("patient-1")
    await svc.finish_turn(
        session.id,
        patient_message="I have fever, chills, and a wet cough for about a week",
        assistant_response="[R] I recommend General Medicine. Urgency: Priority.",
        is_recommendation=True,
    )

    result = await svc.generate_summary(
        session_id=session.id,
        requester_id="doctor-1",
        role="doctor",
        llm_client=FakeLLMClient(None),
    )

    assert result["chief_complaint"] == "I have fever, chills, and a wet cough for about a week"
    assert "fever" in result["reported_symptoms"]
    assert any("cough" in symptom for symptom in result["reported_symptoms"])
    assert result["duration"] == "a week"
    assert "acute respiratory infection" in result["suspected_conditions"]
    assert "fever" in result["clinical_reasoning"]
    assert "wet cough" in result["clinical_reasoning"]
    assert result["recommended_department"] == "General Medicine"
    assert result["urgency_level"] == "Priority"
    assert "General Medicine is appropriate" in result["department_reasoning"]


# ─────────────────────────────────────────────────────────────────────────────
#  Test 3: Schema validation — TriageSummaryResponse accepts new fields
# ─────────────────────────────────────────────────────────────────────────────

def test_triage_summary_response_schema_accepts_new_fields():
    from presentation.schema import TriageSummaryResponse

    response = TriageSummaryResponse(
        chief_complaint="Test complaint",
        reported_symptoms=["symptom1"],
        duration="3 days",
        severity="moderate",
        suspected_conditions=["condition1"],
        department_reasoning="Reasoning here",
        recommended_department="Cardiology",
        urgency_level="Priority",
        patient_description="Patient verbatim quote",
        clinical_reasoning="Clinical reasoning text",
        session_id="sess-123",
        triage_status="PENDING_REVIEW",
    )

    assert response.patient_description == "Patient verbatim quote"
    assert response.clinical_reasoning == "Clinical reasoning text"


def test_triage_summary_response_defaults_new_fields_to_empty():
    from presentation.schema import TriageSummaryResponse

    response = TriageSummaryResponse(
        chief_complaint="Test",
    )

    assert response.patient_description == ""
    assert response.clinical_reasoning == ""


# ─────────────────────────────────────────────────────────────────────────────
#  Test 4: Doctor can call summary; patient gets AccessDenied
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_summary_doctor_can_access():
    svc = _make_service()
    session = await svc.start_session("patient-1")
    await svc.finish_turn(
        session.id, "Đau bụng", "[R] Nội tổng quát. Thông thường.", True
    )

    fake_llm = FakeLLMClient({
        "chief_complaint": "Abdominal pain",
        "reported_symptoms": ["Abdominal pain"],
        "duration": "1 day",
        "severity": "Mild",
        "suspected_conditions": ["Gastroenteritis"],
        "department_reasoning": "Symptoms suggest a GI condition.",
        "recommended_department": "Internal Medicine",
        "urgency_level": "Routine",
        "patient_description": "Đau bụng từ hôm qua",
        "clinical_reasoning": "Acute abdominal pain without red flags suggests gastroenteritis.",
    })

    result = await svc.generate_summary(
        session_id=session.id,
        requester_id="doctor-1",
        role="doctor",
        llm_client=fake_llm,
    )

    assert result["chief_complaint"] == "Abdominal pain"


@pytest.mark.asyncio
async def test_generate_summary_patient_role_raises_access_denied():
    svc = _make_service()
    session = await svc.start_session("patient-1")

    with pytest.raises(TriageSessionAccessDenied):
        await svc.generate_summary(
            session_id=session.id,
            requester_id="patient-1",
            role="patient",
            llm_client=FakeLLMClient({}),
        )


@pytest.mark.asyncio
async def test_generate_summary_admin_role_can_access():
    svc = _make_service()
    session = await svc.start_session("patient-1")
    await svc.finish_turn(
        session.id, "Đau ngực", "[R] Tim mạch. Thông thường.", True
    )

    fake_llm = FakeLLMClient({
        "chief_complaint": "Chest pain",
        "reported_symptoms": ["Chest pain"],
        "duration": "1 hour",
        "severity": "Moderate",
        "suspected_conditions": ["Angina pectoris"],
        "department_reasoning": "Symptoms point to cardiology.",
        "recommended_department": "Cardiology",
        "urgency_level": "Routine",
        "patient_description": "Đau ngực 1 giờ nay",
        "clinical_reasoning": "Chest pain with a known cardiac history suggests angina.",
    })

    result = await svc.generate_summary(
        session_id=session.id,
        requester_id="admin-1",
        role="admin",
        llm_client=fake_llm,
    )

    assert result["chief_complaint"] == "Chest pain"
