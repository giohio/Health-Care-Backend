"""
ChatSessionService — manages lifecycle of lab_chat and clinical_assist sessions.

Responsibilities:
  • Create a new session for any authenticated user.
  • Load an existing session and validate access rights.
  • Persist completed turns (user message + AI response).
"""

import logging
import uuid
from typing import Optional

from Domain.entities import ChatSession
from infrastructure.repositories.chat_session_repository import ChatSessionRepository

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  Custom exceptions
# ──────────────────────────────────────────────────────────────


class ChatSessionNotFound(Exception):
    def __init__(self, session_id: str):
        super().__init__(f"Chat session {session_id!r} not found")


class ChatSessionAccessDenied(Exception):
    """Raised when a patient tries to access another user's session."""


#  Service


class ChatSessionService:

    def __init__(self, repo: ChatSessionRepository):
        self._repo = repo

    # ── Create ────────────────────────────────────────────────

    async def start_session(
        self,
        user_id:      str,
        user_role:    str,
        session_type: str,
        patient_id:   Optional[str] = None,
        department:   Optional[str] = None,
    ) -> ChatSession:
        """Create a new empty chat session."""
        entity = ChatSession(
            id           = str(uuid.uuid4()),
            user_id      = user_id,
            user_role    = user_role,
            session_type = session_type,
            messages     = [],
            patient_id   = patient_id,
            department   = department,
        )
        return await self._repo.save(entity)

    # ── Load ──────────────────────────────────────────────────

    async def load_session(
        self,
        session_id: str,
        user_id:    str,
        user_role:  str,
    ) -> ChatSession:
        """
        Fetch an existing session, enforcing ownership for patient role.
        Doctors and admins can access any session.
        """
        session = await self._repo.get_by_id(session_id)
        if not session:
            raise ChatSessionNotFound(session_id)
        if user_role == "patient" and session.user_id != user_id:
            raise ChatSessionAccessDenied(
                f"Patient {user_id!r} cannot access session {session_id!r}"
            )
        return session

    # ── Persist turn ──────────────────────────────────────────

    async def finish_turn(
        self,
        session:      ChatSession,
        user_message: str,
        ai_response:  str,
    ) -> ChatSession:
        """Append the user message and AI response to the session messages and save."""
        session.messages.append({"role": "user",      "content": user_message})
        session.messages.append({"role": "assistant",  "content": ai_response})
        return await self._repo.save(session)
