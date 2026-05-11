import uuid
from typing import List, Optional

from Domain.entities.clinical_note import ClinicalNote
from Domain.interfaces.clinical_note_repository import IClinicalNoteRepository
from infrastructure.database.models import ClinicalNoteModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


class ClinicalNoteRepository(IClinicalNoteRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_entity(model: ClinicalNoteModel) -> ClinicalNote:
        return ClinicalNote(
            id=model.id,
            patient_id=model.patient_id,
            doctor_id=model.doctor_id,
            appointment_id=model.appointment_id,
            note_type=model.note_type,
            content=model.content,
            is_ai_generated=model.is_ai_generated,
            created_at=model.created_at,
        )

    # ------------------------------------------------------------------
    # Interface implementation
    # ------------------------------------------------------------------

    async def save(self, note: ClinicalNote) -> ClinicalNote:
        # Historical note creation always inserts. Use upsert_current when the
        # caller wants one current note per appointment/type.
        model = ClinicalNoteModel(
            id=note.id,
            patient_id=note.patient_id,
            doctor_id=note.doctor_id,
            appointment_id=note.appointment_id,
            note_type=note.note_type,
            content=note.content,
            is_ai_generated=note.is_ai_generated,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, note_id: uuid.UUID) -> Optional[ClinicalNote]:
        result = await self.session.execute(
            select(ClinicalNoteModel).where(ClinicalNoteModel.id == note_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def update_content(self, note_id: uuid.UUID, content: str) -> Optional[ClinicalNote]:
        result = await self.session.execute(
            select(ClinicalNoteModel).where(ClinicalNoteModel.id == note_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.content = content
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def upsert_current(self, note: ClinicalNote) -> ClinicalNote:
        result = await self.session.execute(
            select(ClinicalNoteModel)
            .where(
                ClinicalNoteModel.patient_id == note.patient_id,
                ClinicalNoteModel.appointment_id == note.appointment_id,
                ClinicalNoteModel.note_type == note.note_type,
            )
            .order_by(ClinicalNoteModel.created_at.desc())
        )
        models = list(result.scalars().all())
        model = models[0] if models else None

        if model is None:
            model = ClinicalNoteModel(
                id=note.id,
                patient_id=note.patient_id,
                doctor_id=note.doctor_id,
                appointment_id=note.appointment_id,
                note_type=note.note_type,
                content=note.content,
                is_ai_generated=note.is_ai_generated,
            )
            self.session.add(model)
        else:
            model.doctor_id = note.doctor_id
            model.content = note.content
            model.is_ai_generated = note.is_ai_generated

            duplicate_ids = [m.id for m in models[1:]]
            if duplicate_ids:
                await self.session.execute(
                    delete(ClinicalNoteModel).where(ClinicalNoteModel.id.in_(duplicate_ids))
                )

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def delete(self, note_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            delete(ClinicalNoteModel).where(ClinicalNoteModel.id == note_id)
        )
        await self.session.flush()
        return (result.rowcount or 0) > 0

    async def list_by_patient(
        self,
        patient_id: uuid.UUID,
        appointment_id: Optional[uuid.UUID] = None,
    ) -> List[ClinicalNote]:
        query = select(ClinicalNoteModel).where(
            ClinicalNoteModel.patient_id == patient_id
        )
        if appointment_id is not None:
            query = query.where(ClinicalNoteModel.appointment_id == appointment_id)
        query = query.order_by(ClinicalNoteModel.created_at.desc())
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]
