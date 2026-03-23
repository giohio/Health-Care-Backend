import uuid
from datetime import date, time
from typing import List, Optional

from Domain.entities.appointment import Appointment
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.value_objects.appointment_status import AppointmentStatus
from infrastructure.database.models import AppointmentModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7


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
            appointment_type=appointment.appointment_type,
            chief_complaint=appointment.chief_complaint,
            note_for_doctor=appointment.note_for_doctor,
            status=appointment.status,
            payment_status=appointment.payment_status,
            confirmed_at=appointment.confirmed_at,
            completed_at=appointment.completed_at,
            cancelled_at=appointment.cancelled_at,
            cancelled_by=appointment.cancelled_by,
            cancelled_by_user_id=(
                uuid.UUID(str(appointment.cancelled_by_user_id)) if appointment.cancelled_by_user_id else None
            ),
            cancel_reason=appointment.cancel_reason,
            queue_number=appointment.queue_number,
            reminder_24h_sent=appointment.reminder_24h_sent,
            reminder_1h_sent=appointment.reminder_1h_sent,
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
                    AppointmentModel.status.in_(
                        [
                            AppointmentStatus.PENDING_PAYMENT,
                            AppointmentStatus.PENDING,
                            AppointmentStatus.CONFIRMED,
                        ]
                    ),
                )
            )
        )
        existing = result.scalar_one_or_none()
        return existing is None

    async def get_by_id_with_lock(self, appointment_id: UUID7) -> Optional[Appointment]:
        result = await self.session.execute(
            select(AppointmentModel).where(AppointmentModel.id == uuid.UUID(str(appointment_id))).with_for_update()
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def is_slot_taken(
        self,
        doctor_id: UUID7,
        appointment_date: date,
        start_time: time,
        end_time: time,
        exclude_id: UUID7 | None = None,
    ) -> bool:
        q = select(func.count()).where(
            and_(
                AppointmentModel.doctor_id == uuid.UUID(str(doctor_id)),
                AppointmentModel.appointment_date == appointment_date,
                AppointmentModel.status.in_(
                    [
                        AppointmentStatus.PENDING_PAYMENT,
                        AppointmentStatus.PENDING,
                        AppointmentStatus.CONFIRMED,
                    ]
                ),
                AppointmentModel.start_time < end_time,
                AppointmentModel.end_time > start_time,
            )
        )
        if exclude_id:
            q = q.where(AppointmentModel.id != uuid.UUID(str(exclude_id)))
        result = await self.session.execute(q)
        return (result.scalar() or 0) > 0

    async def get_next_queue_number(self, doctor_id: UUID7, appointment_date: date) -> int:
        result = await self.session.execute(
            select(func.count()).where(
                and_(
                    AppointmentModel.doctor_id == uuid.UUID(str(doctor_id)),
                    AppointmentModel.appointment_date == appointment_date,
                    AppointmentModel.status == AppointmentStatus.CONFIRMED,
                )
            )
        )
        return (result.scalar() or 0) + 1

    async def get_doctor_queue(
        self,
        doctor_id: UUID7,
        appointment_date: date,
    ) -> list[Appointment]:
        result = await self.session.execute(
            select(AppointmentModel)
            .where(
                and_(
                    AppointmentModel.doctor_id == uuid.UUID(str(doctor_id)),
                    AppointmentModel.appointment_date == appointment_date,
                    AppointmentModel.status.in_(
                        [
                            AppointmentStatus.PENDING,
                            AppointmentStatus.CONFIRMED,
                            AppointmentStatus.COMPLETED,
                            AppointmentStatus.NO_SHOW,
                        ]
                    ),
                )
            )
            .order_by(
                (AppointmentModel.status == AppointmentStatus.PENDING).desc(),
                AppointmentModel.start_time.asc(),
            )
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def get_booked_slots(
        self,
        doctor_id: UUID7,
        appointment_date: date,
    ) -> list[tuple[time, time]]:
        result = await self.session.execute(
            select(AppointmentModel.start_time, AppointmentModel.end_time).where(
                and_(
                    AppointmentModel.doctor_id == uuid.UUID(str(doctor_id)),
                    AppointmentModel.appointment_date == appointment_date,
                    AppointmentModel.status.in_(
                        [
                            AppointmentStatus.PENDING_PAYMENT,
                            AppointmentStatus.PENDING,
                            AppointmentStatus.CONFIRMED,
                        ]
                    ),
                )
            )
        )
        return result.all()

    def _to_entity(self, model: AppointmentModel) -> Appointment:
        return Appointment(
            id=UUID7(str(model.id)),
            patient_id=UUID7(str(model.patient_id)),
            doctor_id=UUID7(str(model.doctor_id)),
            specialty_id=UUID7(str(model.specialty_id)),
            appointment_date=model.appointment_date,
            start_time=model.start_time,
            end_time=model.end_time,
            appointment_type=model.appointment_type,
            chief_complaint=model.chief_complaint,
            note_for_doctor=model.note_for_doctor,
            status=model.status,
            payment_status=model.payment_status,
            confirmed_at=model.confirmed_at,
            completed_at=model.completed_at,
            cancelled_at=model.cancelled_at,
            cancelled_by=model.cancelled_by,
            cancelled_by_user_id=(UUID7(str(model.cancelled_by_user_id)) if model.cancelled_by_user_id else None),
            cancel_reason=model.cancel_reason,
            queue_number=model.queue_number,
            reminder_24h_sent=model.reminder_24h_sent,
            reminder_1h_sent=model.reminder_1h_sent,
        )
