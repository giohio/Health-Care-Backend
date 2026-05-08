import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from Domain.entities import ChatSession
from infrastructure.database.models import ChatSessionModel


class ChatSessionRepository:

    def __init__(self, session: AsyncSession):
        self._session = session

    # ------------------------------------------------------------------ #
    #  Write                                                               #
    # ------------------------------------------------------------------ #

    async def save(self, entity: ChatSession) -> ChatSession:
        result = await self._session.execute(
            select(ChatSessionModel).where(
                ChatSessionModel.id == uuid.UUID(entity.id)
            )
        )
        model = result.scalar_one_or_none()

        if model:
            model.messages   = entity.messages
            model.patient_id = entity.patient_id
            model.department = entity.department
        else:
            model = ChatSessionModel(
                id           = uuid.UUID(entity.id),
                user_id      = entity.user_id,
                user_role    = entity.user_role,
                session_type = entity.session_type,
                messages     = entity.messages,
                patient_id   = entity.patient_id,
                department   = entity.department,
            )
            self._session.add(model)

        await self._session.flush()
        return self._to_entity(model)

    # ------------------------------------------------------------------ #
    #  Read                                                                #
    # ------------------------------------------------------------------ #

    async def get_by_id(self, session_id: str) -> Optional[ChatSession]:
        result = await self._session.execute(
            select(ChatSessionModel).where(
                ChatSessionModel.id == uuid.UUID(session_id)
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    # ------------------------------------------------------------------ #
    #  Mapper                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_entity(model: ChatSessionModel) -> ChatSession:
        return ChatSession(
            id           = str(model.id),
            user_id      = model.user_id,
            user_role    = model.user_role,
            session_type = model.session_type,
            messages     = list(model.messages) if model.messages else [],
            patient_id   = model.patient_id,
            department   = model.department,
            created_at   = model.created_at,
            updated_at   = model.updated_at,
        )
