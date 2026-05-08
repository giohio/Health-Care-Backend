from datetime import date, datetime, time, timedelta

from Application.dtos import AdjustAppointmentRequest, AppointmentResponse
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    UnauthorizedActionError,
    InvalidStatusTransitionError,
)
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.interfaces.event_publisher import IEventPublisher
from Domain.value_objects.appointment_status import AppointmentStatus
from uuid_extension import UUID7


class AdjustAppointmentUseCase:
    def __init__(self, session, appointment_repo: IAppointmentRepository, event_publisher: IEventPublisher):
        self.session = session
        self.appointment_repo = appointment_repo
        self.event_publisher = event_publisher

    async def execute(
        self,
        appointment_id: UUID7,
        doctor_id: UUID7,
        request: AdjustAppointmentRequest,
    ) -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id_with_lock(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()

        if not appointment.can_be_adjusted_by(doctor_id):
            raise UnauthorizedActionError(
                "Only the assigned doctor can adjust an active appointment"
            )

        # Compute new end_time from duration_minutes
        base = datetime.combine(date.min, appointment.start_time)
        new_end_dt = base + timedelta(minutes=request.duration_minutes)
        new_end_time: time = new_end_dt.time()

        if new_end_time <= appointment.start_time:
            raise InvalidStatusTransitionError(
                "duration_minutes must produce an end_time after start_time"
            )

        old_end_time = appointment.end_time
        appointment.end_time = new_end_time

        if request.consultation_fee is not None:
            appointment.consultation_fee = request.consultation_fee

        await self.appointment_repo.save(appointment)

        # Compute delay in minutes (positive = extended, negative = shortened)
        old_end_dt = datetime.combine(date.min, old_end_time)
        delay_minutes = int((new_end_dt - old_end_dt).total_seconds() // 60)

        # Build affected-patients list for notifications
        affected_patients = []
        if delay_minutes != 0:
            queue = await self.appointment_repo.get_doctor_queue(
                doctor_id=appointment.doctor_id,
                appointment_date=appointment.appointment_date,
            )
            for appt in sorted(
                (a for a in queue if
                 a.status == AppointmentStatus.CONFIRMED and
                 a.start_time > appointment.start_time and
                 str(a.id) != str(appointment.id)),
                key=lambda a: a.start_time,
            ):
                orig_start_dt = datetime.combine(date.min, appt.start_time)
                orig_end_dt = datetime.combine(date.min, appt.end_time)
                new_start_dt = orig_start_dt + timedelta(minutes=delay_minutes)
                new_end_dt_appt = orig_end_dt + timedelta(minutes=delay_minutes)
                appt.start_time = new_start_dt.time()
                appt.end_time = new_end_dt_appt.time()
                await self.appointment_repo.save(appt)
                affected_patients.append({
                    "patient_id": str(appt.patient_id),
                    "appointment_id": str(appt.id),
                    "original_start_time": orig_start_dt.time().strftime("%H:%M"),
                    "new_estimated_start_time": new_start_dt.time().strftime("%H:%M"),
                })

        await self.event_publisher.publish(
            session=self.session,
            aggregate_id=appointment.id,
            aggregate_type="appointment_events",
            event_type="appointment.adjusted",
            payload={
                "appointment_id": str(appointment.id),
                "doctor_id": str(appointment.doctor_id),
                "patient_id": str(appointment.patient_id),
                "appointment_date": str(appointment.appointment_date),
                "new_end_time": new_end_time.strftime("%H:%M"),
                "old_end_time": old_end_time.strftime("%H:%M"),
                "delay_minutes": delay_minutes,
                "affected_patients": affected_patients,
            },
        )
        await self.session.commit()
        return AppointmentResponse.model_validate(appointment)
