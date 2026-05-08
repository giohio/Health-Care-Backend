import uuid
from typing import Optional

from Domain.entities.appointment_lab_summary import AppointmentLabSummary
from Domain.interfaces.appointment_summary_repository import IAppointmentSummaryRepository
from infrastructure.database.models import AppointmentLabSummaryModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class AppointmentSummaryRepository(IAppointmentSummaryRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(model: AppointmentLabSummaryModel) -> AppointmentLabSummary:
        return AppointmentLabSummary(
            id=model.id,
            appointment_id=model.appointment_id,
            patient_id=model.patient_id,
            status=model.status,
            ai_holistic_text=model.ai_holistic_text,
            total_results=model.total_results,
            created_at=model.created_at,
            updated_at=model.updated_at,
            doctor_conclusion=model.doctor_conclusion,
            reviewed_by=model.reviewed_by,
            reviewed_at=model.reviewed_at,
        )

    async def save(self, summary: AppointmentLabSummary) -> AppointmentLabSummary:
        db = await self.session.execute(
            select(AppointmentLabSummaryModel).where(
                AppointmentLabSummaryModel.appointment_id == summary.appointment_id
            )
        )
        model = db.scalar_one_or_none()

        if model:
            model.status = summary.status
            model.ai_holistic_text = summary.ai_holistic_text
            model.total_results = summary.total_results
            model.doctor_conclusion = summary.doctor_conclusion
            model.reviewed_by = summary.reviewed_by
            model.reviewed_at = summary.reviewed_at
        else:
            model = AppointmentLabSummaryModel(
                id=summary.id,
                appointment_id=summary.appointment_id,
                patient_id=summary.patient_id,
                status=summary.status,
                ai_holistic_text=summary.ai_holistic_text,
                total_results=summary.total_results,
            )
            self.session.add(model)

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_appointment_id(self, appointment_id: uuid.UUID) -> Optional[AppointmentLabSummary]:
        db = await self.session.execute(
            select(AppointmentLabSummaryModel).where(
                AppointmentLabSummaryModel.appointment_id == appointment_id
            )
        )
        model = db.scalar_one_or_none()
        return self._to_entity(model) if model else None
