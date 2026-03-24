from Application.dtos import AppointmentResponse
from Application.use_cases._helpers import add_minutes
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
    SlotNotAvailableError,
    UnauthorizedActionError,
)
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.interfaces.event_publisher import IEventPublisher
from Domain.value_objects.appointment_status import AppointmentStatus
from uuid_extension import UUID7


class RescheduleAppointmentUseCase:
    def __init__(
        self,
        session,
        lock_manager,
        appointment_repo: IAppointmentRepository,
        doctor_client,
        event_publisher: IEventPublisher,
    ):
        self.session = session
        self.lock_manager = lock_manager
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client
        self.event_publisher = event_publisher

    async def execute(self, appointment_id: UUID7, patient_id: UUID7, new_date, new_time) -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id_with_lock(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()

        if not appointment.can_be_rescheduled_by(patient_id):
            raise UnauthorizedActionError("Only owning patient can reschedule this appointment")

        if appointment.status not in (
            AppointmentStatus.PENDING_PAYMENT,
            AppointmentStatus.PENDING,
            AppointmentStatus.CONFIRMED,
        ):
            raise InvalidStatusTransitionError("Appointment cannot be rescheduled from current status")

        lock_token = await self.lock_manager.acquire_slot(
            str(appointment.doctor_id),
            str(new_date),
            str(new_time),
        )
        if not lock_token:
            raise SlotNotAvailableError("Requested slot is being booked by another request")

        try:
            config = await self.doctor_client.get_type_config(
                str(appointment.specialty_id),
                appointment.appointment_type,
            )
            duration_minutes = (config or {}).get("duration_minutes", 30)
            new_end_time = add_minutes(new_time, duration_minutes)

            taken = await self.appointment_repo.is_slot_taken(
                doctor_id=appointment.doctor_id,
                appointment_date=new_date,
                start_time=new_time,
                end_time=new_end_time,
                exclude_id=appointment.id,
            )
            if taken:
                raise SlotNotAvailableError("Requested slot is no longer available")

            old_date = appointment.appointment_date
            old_time = appointment.start_time
            old_end_time = appointment.end_time

            appointment.appointment_date = new_date
            appointment.start_time = new_time
            appointment.end_time = new_end_time
            appointment.queue_number = None
            if appointment.status == AppointmentStatus.CONFIRMED:
                appointment.status = AppointmentStatus.PENDING
                appointment.confirmed_at = None
            await self.appointment_repo.save(appointment)

            await self.event_publisher.publish(
                session=self.session,
                aggregate_id=appointment.id,
                aggregate_type="appointment_events",
                event_type="appointment.rescheduled",
                payload={
                    "appointment_id": str(appointment.id),
                    "patient_id": str(appointment.patient_id),
                    "doctor_id": str(appointment.doctor_id),
                    "old_date": str(old_date),
                    "old_start_time": str(old_time),
                    "old_end_time": str(old_end_time),
                    "new_date": str(new_date),
                    "new_start_time": str(new_time),
                    "new_end_time": str(new_end_time),
                },
            )
            await self.event_publisher.publish(
                session=self.session,
                aggregate_id=appointment.id,
                aggregate_type="cache_events",
                event_type="cache.invalidate",
                payload={
                    "patterns": [
                        f"slots:{appointment.doctor_id}:{old_date}:*",
                        f"slots:{appointment.doctor_id}:{new_date}:*",
                        f"queue:{appointment.doctor_id}:{old_date}",
                        f"queue:{appointment.doctor_id}:{new_date}",
                    ]
                },
            )
            await self.session.commit()
            return AppointmentResponse.model_validate(appointment)
        finally:
            await self.lock_manager.release_slot(
                str(appointment.doctor_id),
                str(new_date),
                str(new_time),
                lock_token,
            )
