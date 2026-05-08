import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from Domain.entities import TriageSession
from Domain.enums import TriageSessionStatus
from Domain.interfaces.triage_session_repository import ITriageSessionRepository
from infrastructure.database.models import TriageSessionModel


class TriageSessionRepository(ITriageSessionRepository):

    def __init__(self, session: AsyncSession):
        self._session = session

    # ------------------------------------------------------------------ #
    #  Write                                                               #
    # ------------------------------------------------------------------ #

    async def save(self, entity: TriageSession) -> TriageSession:
        result = await self._session.execute(
            select(TriageSessionModel).where(
                TriageSessionModel.id == uuid.UUID(entity.id)
            )
        )
        model = result.scalar_one_or_none()

        if model:
            model.status               = entity.status
            model.messages             = entity.messages
            model.suggested_department = entity.suggested_department
            model.urgency_level        = entity.urgency_level
            model.doctor_id            = entity.doctor_id
            model.final_department     = entity.final_department
            model.doctor_notes         = entity.doctor_notes
            model.completed_at         = entity.completed_at
            model.appointment_id       = getattr(entity, 'appointment_id', None)
            model.pending_booking       = getattr(entity, 'pending_booking', None)
        else:
            model = TriageSessionModel(
                id                   = uuid.UUID(entity.id),
                patient_id           = entity.patient_id,
                status               = entity.status,
                messages             = entity.messages,
                suggested_department = entity.suggested_department,
                urgency_level        = entity.urgency_level,
                doctor_id            = entity.doctor_id,
                final_department     = entity.final_department,
                doctor_notes         = entity.doctor_notes,
                completed_at         = entity.completed_at,
                appointment_id       = getattr(entity, 'appointment_id', None),
                pending_booking       = getattr(entity, 'pending_booking', None),
            )
            self._session.add(model)

        await self._session.flush()
        # Do NOT call _to_entity here — the model is still attached to an
        # AsyncSession whose onupdate hooks may lazily load expired columns
        # (e.g. updated_at) outside an async greenlet, causing
        # sqlalchemy.exc.MissingGreenlet.  We already have every field
        # from the entity; return it directly.
        return TriageSession(
            id                   = entity.id,
            patient_id           = entity.patient_id,
            status               = entity.status,
            messages             = entity.messages,
            suggested_department = entity.suggested_department,
            urgency_level        = entity.urgency_level,
            doctor_id            = entity.doctor_id,
            final_department     = entity.final_department,
            doctor_notes         = entity.doctor_notes,
            created_at           = model.created_at,
            updated_at           = None,   # caller already holds the entity
            completed_at         = entity.completed_at,
            appointment_id       = getattr(entity, 'appointment_id', None),
            pending_booking       = getattr(entity, 'pending_booking', None),
        )

    # ------------------------------------------------------------------ #
    #  Read                                                                #
    # ------------------------------------------------------------------ #

    async def get_by_id(self, session_id: str) -> Optional[TriageSession]:
        result = await self._session.execute(
            select(TriageSessionModel).where(
                TriageSessionModel.id == uuid.UUID(session_id)
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_patient(self, patient_id: str) -> list[TriageSession]:
        result = await self._session.execute(
            select(TriageSessionModel)
            .where(TriageSessionModel.patient_id == patient_id)
            .order_by(TriageSessionModel.created_at.desc())
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_all(self, status_filter: Optional[str] = None) -> list[TriageSession]:
        query = select(TriageSessionModel).order_by(TriageSessionModel.created_at.desc())
        if status_filter:
            query = query.where(TriageSessionModel.status == status_filter)
        result = await self._session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    # ------------------------------------------------------------------ #
    #  Mapper                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_entity(model: TriageSessionModel) -> TriageSession:
        return TriageSession(
            id                   = str(model.id),
            patient_id           = model.patient_id,
            status               = model.status,
            messages             = list(model.messages) if model.messages else [],
            suggested_department = model.suggested_department,
            urgency_level        = model.urgency_level,
            doctor_id            = model.doctor_id,
            final_department     = model.final_department,
            doctor_notes         = model.doctor_notes,
            created_at           = model.created_at,
            updated_at           = model.updated_at,
            completed_at         = model.completed_at,
            appointment_id       = model.appointment_id,
            pending_booking      = model.pending_booking,
        )
