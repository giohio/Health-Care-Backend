"""
Unit tests for Application/chat_session.py — ChatSessionService.

External DB is replaced with a simple in-memory fake repository.
Covers: start_session, load_session (access denied, not found), finish_turn.
"""

import pytest
from typing import Optional

from Application.chat_session import (
    ChatSessionAccessDenied,
    ChatSessionNotFound,
    ChatSessionService,
)
from Domain.entities import ChatSession
from infrastructure.repositories.chat_session_repository import ChatSessionRepository


# ────────────────────────────────────────────────────────────────────────────
#  Fake In-Memory Repository
# ────────────────────────────────────────────────────────────────────────────

class FakeChatSessionRepo:
    def __init__(self):
        self._store: dict[str, ChatSession] = {}

    async def save(self, entity: ChatSession) -> ChatSession:
        self._store[entity.id] = entity
        return entity

    async def get_by_id(self, session_id: str) -> Optional[ChatSession]:
        return self._store.get(session_id)


def make_service() -> ChatSessionService:
    return ChatSessionService(FakeChatSessionRepo())


# ────────────────────────────────────────────────────────────────────────────
#  start_session
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_session_creates_new_session():
    svc = make_service()
    session = await svc.start_session(
        user_id="u-001", user_role="patient", session_type="lab_chat"
    )
    assert session.id
    assert session.user_id == "u-001"
    assert session.user_role == "patient"
    assert session.session_type == "lab_chat"
    assert session.messages == []


@pytest.mark.asyncio
async def test_start_session_stores_optional_fields():
    svc = make_service()
    session = await svc.start_session(
        user_id="d-001",
        user_role="doctor",
        session_type="clinical_assist",
        patient_id="p-007",
        department="cardiology",
    )
    assert session.patient_id == "p-007"
    assert session.department == "cardiology"


@pytest.mark.asyncio
async def test_start_session_unique_ids():
    svc = make_service()
    s1 = await svc.start_session("u-001", "patient", "lab_chat")
    s2 = await svc.start_session("u-001", "patient", "lab_chat")
    assert s1.id != s2.id


# ────────────────────────────────────────────────────────────────────────────
#  load_session
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_load_session_returns_existing():
    svc = make_service()
    created = await svc.start_session("u-001", "patient", "lab_chat")
    loaded  = await svc.load_session(created.id, "u-001", "patient")
    assert loaded.id == created.id


@pytest.mark.asyncio
async def test_load_session_not_found_raises():
    svc = make_service()
    with pytest.raises(ChatSessionNotFound):
        await svc.load_session("non-existent-id", "u-001", "patient")


@pytest.mark.asyncio
async def test_load_session_patient_cannot_access_others_session():
    svc = make_service()
    session = await svc.start_session("u-001", "patient", "lab_chat")
    with pytest.raises(ChatSessionAccessDenied):
        await svc.load_session(session.id, "u-002", "patient")


@pytest.mark.asyncio
async def test_load_session_doctor_can_access_any_session():
    svc = make_service()
    session = await svc.start_session("u-001", "patient", "lab_chat")
    # Doctor with different user_id should succeed
    loaded = await svc.load_session(session.id, "d-001", "doctor")
    assert loaded.id == session.id


@pytest.mark.asyncio
async def test_load_session_admin_can_access_any_session():
    svc = make_service()
    session = await svc.start_session("u-001", "patient", "lab_chat")
    loaded = await svc.load_session(session.id, "admin-001", "admin")
    assert loaded.id == session.id


# ────────────────────────────────────────────────────────────────────────────
#  finish_turn
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_finish_turn_appends_both_messages():
    svc = make_service()
    session = await svc.start_session("u-001", "patient", "lab_chat")
    updated = await svc.finish_turn(session, "What does CBC mean?", "CBC stands for...")

    assert len(updated.messages) == 2
    assert updated.messages[0] == {"role": "user",      "content": "What does CBC mean?"}
    assert updated.messages[1] == {"role": "assistant",  "content": "CBC stands for..."}


@pytest.mark.asyncio
async def test_finish_turn_accumulates_across_multiple_turns():
    svc = make_service()
    session = await svc.start_session("u-001", "patient", "lab_chat")

    session = await svc.finish_turn(session, "First question", "First answer")
    session = await svc.finish_turn(session, "Second question", "Second answer")

    assert len(session.messages) == 4
    assert session.messages[2]["content"] == "Second question"
    assert session.messages[3]["content"] == "Second answer"


@pytest.mark.asyncio
async def test_finish_turn_persists_to_repo():
    repo = FakeChatSessionRepo()
    svc  = ChatSessionService(repo)
    session = await svc.start_session("u-001", "patient", "lab_chat")
    await svc.finish_turn(session, "q", "a")

    stored = await repo.get_by_id(session.id)
    assert stored is not None
    assert len(stored.messages) == 2
