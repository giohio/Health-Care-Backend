"""
Unit tests for Application/triage_session.py

Tests TriageSessionService using a fake in-memory repository.
Covers: start_session, load_session, finish_turn, doctor_confirm,
doctor_refer_internal, list_sessions, urgency auto-confirm logic.
"""

import pytest
from typing import Optional

from Application.triage_session import (
    TriageSessionAccessDenied,
    TriageSessionNotFound,
    TriageSessionService,
    _parse_urgency,
    _parse_department,
)
from Domain.entities import TriageSession
from Domain.enums import Department, TriageSessionStatus
from Domain.interfaces.triage_session_repository import ITriageSessionRepository


# ────────────────────────────────────────────────────────────────────────────
#  Fake In-Memory Repository
# ────────────────────────────────────────────────────────────────────────────

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


# ────────────────────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────────────────────

def make_service():
    return TriageSessionService(FakeTriageSessionRepo())


# ────────────────────────────────────────────────────────────────────────────
#  Parse helpers
# ────────────────────────────────────────────────────────────────────────────

def test_parse_urgency_routine_vi():
    assert _parse_urgency("Mức độ ưu tiên: Thông thường.") == "Routine"


def test_parse_urgency_routine_en():
    assert _parse_urgency("Priority level: Routine.") == "Routine"


def test_parse_urgency_priority_vi():
    assert _parse_urgency("Mức độ ưu tiên: Ưu tiên — nên khám sớm.") == "Priority"


def test_parse_urgency_emergency_vi():
    assert _parse_urgency("Đây là trường hợp Cấp cứu, hãy gọi ngay.") == "Emergency"


def test_parse_urgency_default_when_no_keyword():
    # No urgency keyword → safe default "Priority"
    assert _parse_urgency("Bạn nên đến khám bác sĩ Tim mạch.") == "Priority"


def test_parse_department_cardiology():
    assert _parse_department("Gợi ý chuyên khoa: Tim mạch") == "Cardiology"


def test_parse_department_internal_vi():
    assert _parse_department("Nội tổng quát để thăm khám ban đầu.") == "General Medicine"


def test_parse_department_none_when_no_match():
    assert _parse_department("Không rõ chuyên khoa phù hợp.") is None


# ────────────────────────────────────────────────────────────────────────────
#  start_session
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_session_creates_active_session():
    svc = make_service()
    session = await svc.start_session("patient-1")

    assert session.id
    assert session.patient_id == "patient-1"
    assert session.status     == TriageSessionStatus.ACTIVE
    assert session.messages   == []


@pytest.mark.asyncio
async def test_start_session_generates_unique_ids():
    svc = make_service()
    s1  = await svc.start_session("patient-1")
    s2  = await svc.start_session("patient-1")
    assert s1.id != s2.id


# ────────────────────────────────────────────────────────────────────────────
#  load_session
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_load_session_returns_session():
    svc     = make_service()
    created = await svc.start_session("patient-1")
    loaded  = await svc.load_session(created.id, "patient-1", "patient")
    assert loaded.id == created.id


@pytest.mark.asyncio
async def test_load_session_not_found():
    svc = make_service()
    with pytest.raises(TriageSessionNotFound):
        await svc.load_session("nonexistent-id", "patient-1", "patient")


@pytest.mark.asyncio
async def test_load_session_access_denied_for_other_patient():
    svc     = make_service()
    created = await svc.start_session("patient-1")
    with pytest.raises(TriageSessionAccessDenied):
        await svc.load_session(created.id, "patient-2", "patient")


@pytest.mark.asyncio
async def test_load_session_doctor_can_access_any_session():
    svc     = make_service()
    created = await svc.start_session("patient-1")
    # Should not raise even though doctor_id != patient_id
    loaded = await svc.load_session(created.id, "doctor-999", "doctor")
    assert loaded.id == created.id


# ────────────────────────────────────────────────────────────────────────────
#  finish_turn
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_finish_turn_appends_messages():
    svc     = make_service()
    session = await svc.start_session("patient-1")

    updated = await svc.finish_turn(
        session_id         = session.id,
        patient_message    = "Tôi bị đau đầu",
        assistant_response = "[Q] Bạn đau ở vị trí nào?",
        is_recommendation  = False,
    )

    assert len(updated.messages)                   == 2
    assert updated.messages[0]["role"]             == "user"
    assert updated.messages[0]["content"]          == "Tôi bị đau đầu"
    assert updated.messages[1]["role"]             == "assistant"
    assert updated.messages[1]["content"]          == "[Q] Bạn đau ở vị trí nào?"
    assert updated.status                          == TriageSessionStatus.ACTIVE


@pytest.mark.asyncio
async def test_finish_turn_routine_urgency_sets_auto_confirmed():
    svc     = make_service()
    session = await svc.start_session("patient-1")

    response = "[R] Gợi ý chuyên khoa Tim mạch. Mức độ ưu tiên: Thông thường."
    updated = await svc.finish_turn(
        session_id         = session.id,
        patient_message    = "Đau ngực nhẹ",
        assistant_response = response,
        is_recommendation  = True,
    )

    assert updated.status           == TriageSessionStatus.AUTO_CONFIRMED
    assert updated.urgency_level    == "Routine"
    assert updated.suggested_department == "Cardiology"
    assert updated.completed_at     is not None


@pytest.mark.asyncio
async def test_finish_turn_priority_urgency_sets_pending_review():
    svc     = make_service()
    session = await svc.start_session("patient-1")

    response = "[R] Gợi ý Thần kinh. Mức độ ưu tiên: Ưu tiên."
    updated = await svc.finish_turn(
        session_id         = session.id,
        patient_message    = "Đau đầu dữ dội",
        assistant_response = response,
        is_recommendation  = True,
    )

    assert updated.status           == TriageSessionStatus.PENDING_REVIEW
    assert updated.urgency_level    == "Priority"
    assert updated.suggested_department == "Neurology"


@pytest.mark.asyncio
async def test_finish_turn_emergency_urgency_sets_pending_review():
    svc     = make_service()
    session = await svc.start_session("patient-1")

    response = "[R] Đây là Cấp cứu — ra Tim mạch ngay."
    updated = await svc.finish_turn(
        session_id         = session.id,
        patient_message    = "Đau ngực dữ dội",
        assistant_response = response,
        is_recommendation  = True,
    )

    assert updated.status        == TriageSessionStatus.PENDING_REVIEW
    assert updated.urgency_level == "Emergency"


@pytest.mark.asyncio
async def test_finish_turn_accumulates_messages_across_multiple_turns():
    svc     = make_service()
    session = await svc.start_session("patient-1")

    await svc.finish_turn(session.id, "Đau đầu",      "[Q] Từ khi nào?", False)
    await svc.finish_turn(session.id, "Từ hôm qua",   "[Q] Đau ở đâu?",  False)
    final = await svc.finish_turn(session.id, "Thái dương", "[R] Tim mạch. Thông thường.", True)

    assert len(final.messages) == 6   # 3 patient + 3 assistant
    assert final.status == TriageSessionStatus.AUTO_CONFIRMED


# ────────────────────────────────────────────────────────────────────────────
#  doctor_confirm
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_doctor_confirm_sets_correct_status_and_department():
    svc     = make_service()
    session = await svc.start_session("patient-1")
    await svc.finish_turn(
        session.id, "Đau ngực", "[R] Tim mạch. Ưu tiên.", True
    )

    confirmed = await svc.doctor_confirm(session.id, "doctor-1", notes="Đồng ý với AI.")

    assert confirmed.status           == TriageSessionStatus.DOCTOR_CONFIRMED
    assert confirmed.doctor_id        == "doctor-1"
    assert confirmed.final_department == confirmed.suggested_department
    assert confirmed.doctor_notes     == "Đồng ý với AI."
    assert confirmed.completed_at     is not None


@pytest.mark.asyncio
async def test_doctor_confirm_not_found():
    svc = make_service()
    with pytest.raises(TriageSessionNotFound):
        await svc.doctor_confirm("nonexistent-id", "doctor-1")


# ────────────────────────────────────────────────────────────────────────────
#  doctor_refer_internal
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_doctor_refer_internal_sets_status_and_department():
    svc     = make_service()
    session = await svc.start_session("patient-1")
    await svc.finish_turn(session.id, "Triệu chứng lạ", "[R] Nội tổng quát. Ưu tiên.", True)

    referred = await svc.doctor_refer_internal(session.id, "doctor-2", notes="Không chắc chắn.")

    assert referred.status           == TriageSessionStatus.REFERRED_INTERNAL
    assert referred.doctor_id        == "doctor-2"
    assert referred.final_department == "Internal Medicine"
    assert referred.doctor_notes     == "Không chắc chắn."
    assert referred.completed_at     is not None


# ────────────────────────────────────────────────────────────────────────────
#  list_sessions
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_sessions_patient_sees_only_own():
    svc = make_service()
    await svc.start_session("patient-1")
    await svc.start_session("patient-1")
    await svc.start_session("patient-2")

    sessions = await svc.list_sessions("patient-1", "patient")
    assert len(sessions) == 2
    assert all(s.patient_id == "patient-1" for s in sessions)


@pytest.mark.asyncio
async def test_list_sessions_doctor_sees_all():
    svc = make_service()
    await svc.start_session("patient-1")
    await svc.start_session("patient-2")

    sessions = await svc.list_sessions("doctor-1", "doctor")
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_list_sessions_doctor_with_status_filter():
    svc = make_service()
    s1  = await svc.start_session("patient-1")
    s2  = await svc.start_session("patient-2")
    # Simulate s1 completed as pending_review
    await svc.finish_turn(s1.id, "msg", "[R] Tim mạch. Ưu tiên.", True)

    pending = await svc.list_sessions("doctor-1", "doctor", status_filter="pending_review")
    assert len(pending) == 1
    assert pending[0].id == s1.id
