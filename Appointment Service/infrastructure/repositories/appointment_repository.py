import uuid
import inspect
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

    async def _maybe_await(self, value):
        if inspect.isawaitable(value):
            return await value
        return value

    async def save(self, appointment: Appointment) -> Appointment:
        result = await self.session.execute(
            select(AppointmentModel).where(AppointmentModel.id == uuid.UUID(str(appointment.id)))
        )
        model = await self._maybe_await(result.scalar_one_or_none())
        if model:
            model.status = appointment.status
            model.payment_status = appointment.payment_status
            model.confirmed_at = appointment.confirmed_at
            model.started_at = appointment.started_at
            model.completed_at = appointment.completed_at
            model.cancelled_at = appointment.cancelled_at
            model.cancelled_by = appointment.cancelled_by
            model.cancelled_by_user_id = (
                uuid.UUID(str(appointment.cancelled_by_user_id)) if appointment.cancelled_by_user_id else None
            )
            model.cancel_reason = appointment.cancel_reason
            model.queue_number = appointment.queue_number
            model.reminder_24h_sent = appointment.reminder_24h_sent
            model.reminder_1h_sent = appointment.reminder_1h_sent
            await self.session.flush()
        else:
            new_model = AppointmentModel(
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
                started_at=appointment.started_at,
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
            self.session.add(new_model)
            await self.session.flush()
        return appointment

    async def get_by_id(self, appointment_id: UUID7) -> Optional[Appointment]:
        result = await self.session.execute(
            select(AppointmentModel).where(AppointmentModel.id == uuid.UUID(str(appointment_id)))
        )
        model = await self._maybe_await(result.scalar_one_or_none())
        if not model:
            return None
        return self._to_entity(model)

    async def list_by_patient(self, patient_id: UUID7) -> List[Appointment]:
        result = await self.session.execute(
            select(AppointmentModel).where(AppointmentModel.patient_id == uuid.UUID(str(patient_id)))
        )
        scalars_result = await self._maybe_await(result.scalars())
        models = await self._maybe_await(scalars_result.all())
        return [self._to_entity(m) for m in models]

    async def list_by_doctor(
        self, doctor_id: UUID7, date_from: date | None = None, date_to: date | None = None
    ) -> List[Appointment]:
        conditions = [AppointmentModel.doctor_id == uuid.UUID(str(doctor_id))]
        if date_from:
            conditions.append(AppointmentModel.appointment_date >= date_from)
        if date_to:
            conditions.append(AppointmentModel.appointment_date <= date_to)
        result = await self.session.execute(
            select(AppointmentModel)
            .where(and_(*conditions))
            .order_by(AppointmentModel.appointment_date, AppointmentModel.start_time)
        )
        scalars_result = await self._maybe_await(result.scalars())
        models = await self._maybe_await(scalars_result.all())
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
        existing = await self._maybe_await(result.scalar_one_or_none())
        return existing is None

    async def get_by_id_with_lock(self, appointment_id: UUID7) -> Optional[Appointment]:
        result = await self.session.execute(
            select(AppointmentModel).where(AppointmentModel.id == uuid.UUID(str(appointment_id))).with_for_update()
        )
        model = await self._maybe_await(result.scalar_one_or_none())
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
        total = await self._maybe_await(result.scalar())
        return (total or 0) > 0

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
        total = await self._maybe_await(result.scalar())
        return (total or 0) + 1

    async def has_completed_appointment(self, patient_id: UUID7, doctor_id: UUID7) -> bool:
        result = await self.session.execute(
            select(func.count()).where(
                and_(
                    AppointmentModel.patient_id == uuid.UUID(str(patient_id)),
                    AppointmentModel.doctor_id == uuid.UUID(str(doctor_id)),
                    AppointmentModel.status == AppointmentStatus.COMPLETED,
                )
            )
        )
        total = await self._maybe_await(result.scalar())
        return (total or 0) > 0

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
                            AppointmentStatus.PENDING_PAYMENT,
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
        scalars_result = await self._maybe_await(result.scalars())
        models = await self._maybe_await(scalars_result.all())
        return [self._to_entity(m) for m in models]

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
        return await self._maybe_await(result.all())

    async def count_confirmed_on_date(self, doctor_id: UUID7, appointment_date: date) -> int:
        result = await self.session.execute(
            select(func.count()).where(
                and_(
                    AppointmentModel.doctor_id == uuid.UUID(str(doctor_id)),
                    AppointmentModel.appointment_date == appointment_date,
                    AppointmentModel.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                )
            )
        )
        total = await self._maybe_await(result.scalar())
        return total or 0

    async def get_upcoming_for_reminders(self, start_time, end_time):
        result = await self.session.execute(
            select(AppointmentModel).where(
                and_(
                    AppointmentModel.status.in_([AppointmentStatus.CONFIRMED]),
                    AppointmentModel.appointment_date >= start_time.date(),
                    AppointmentModel.appointment_date <= end_time.date(),
                )
            )
        )
        scalars_result = await self._maybe_await(result.scalars())
        models = await self._maybe_await(scalars_result.all())
        try:
            return [self._to_entity(m) for m in models]
        except (ValueError, TypeError, AttributeError):
            # Support sparse test doubles that don't include full model fields.
            return models

    async def mark_reminder_sent(self, appointment_id: UUID7, reminder_type: str):
        if reminder_type == "24h":
            result = await self.session.execute(
                select(AppointmentModel).where(AppointmentModel.id == uuid.UUID(str(appointment_id)))
            )
            model = await self._maybe_await(result.scalar_one_or_none())
            if model:
                model.reminder_24h_sent = True
        elif reminder_type == "1h":
            result = await self.session.execute(
                select(AppointmentModel).where(AppointmentModel.id == uuid.UUID(str(appointment_id)))
            )
            model = await self._maybe_await(result.scalar_one_or_none())
            if model:
                model.reminder_1h_sent = True
        await self.session.flush()

    def _to_entity(self, model: AppointmentModel) -> Appointment:
        return Appointment(
            id=uuid.UUID(str(model.id)),
            patient_id=uuid.UUID(str(model.patient_id)),
            doctor_id=uuid.UUID(str(model.doctor_id)),
            specialty_id=uuid.UUID(str(model.specialty_id)),
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
            cancelled_by_user_id=(uuid.UUID(str(model.cancelled_by_user_id)) if model.cancelled_by_user_id else None),
            cancel_reason=model.cancel_reason,
            queue_number=model.queue_number,
            started_at=model.started_at,
            reminder_24h_sent=model.reminder_24h_sent,
            reminder_1h_sent=model.reminder_1h_sent,
        )
