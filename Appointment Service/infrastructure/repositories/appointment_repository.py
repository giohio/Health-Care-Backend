from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional
from Domain.entities.appointment import Appointment
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.value_objects.appointment_status import AppointmentStatus
from infrastructure.database.models import AppointmentModel
from uuid_extension import UUID7
import uuid
from datetime import date, time

class AppointmentRepository(IAppointmentRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, appointment: Appointment) -> Appointment:
        model = AppointmentModel(
            id=uuid.UUID(str(appointment.id)),
            patient_id=uuid.UUID(str(appointment.patient_id)),
            doctor_id=uuid.UUID(str(appointment.doctor_id)),
            specialty_id=uuid.UUID(str(appointment.specialty_id)),
            appointment_date=appointment.appointment_date,
            start_time=appointment.start_time,
            end_time=appointment.end_time,
            status=appointment.status,
            payment_status=appointment.payment_status
        )
        await self.session.merge(model)
        return appointment

    async def get_by_id(self, appointment_id: UUID7) -> Optional[Appointment]:
        result = await self.session.execute(
            select(AppointmentModel).where(AppointmentModel.id == uuid.UUID(str(appointment_id)))
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def list_by_patient(self, patient_id: UUID7) -> List[Appointment]:
        result = await self.session.execute(
            select(AppointmentModel).where(AppointmentModel.patient_id == uuid.UUID(str(patient_id)))
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def check_doctor_availability(self, doctor_id: UUID7, appointment_date: date, start_time: time) -> bool:
        # Check if there is any PENDING or CONFIRMED appointment for this doctor at this time
        result = await self.session.execute(
            select(AppointmentModel).where(
                and_(
                    AppointmentModel.doctor_id == uuid.UUID(str(doctor_id)),
                    AppointmentModel.appointment_date == appointment_date,
                    AppointmentModel.start_time == start_time,
                    AppointmentModel.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED])
                )
            )
        )
        existing = result.scalar_one_or_none()
        return existing is None

    def _to_entity(self, model: AppointmentModel) -> Appointment:
        return Appointment(
            id=UUID7(str(model.id)),
            patient_id=UUID7(str(model.patient_id)),
            doctor_id=UUID7(str(model.doctor_id)),
            specialty_id=UUID7(str(model.specialty_id)),
            appointment_date=model.appointment_date,
            start_time=model.start_time,
            end_time=model.end_time,
            status=model.status,
            payment_status=model.payment_status
        )
