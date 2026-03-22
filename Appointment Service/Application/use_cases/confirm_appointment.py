from uuid_extension import UUID7

from healthai_db import OutboxWriter

from Application.dtos import AppointmentResponse
from Application.use_cases._helpers import utcnow
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    UnauthorizedActionError,
    InvalidStatusTransitionError,
)
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.value_objects.appointment_status import AppointmentStatus


class ConfirmAppointmentUseCase:
    def __init__(self, session, appointment_repo: IAppointmentRepository):
        self.session = session
        self.appointment_repo = appointment_repo

    async def execute(self, appointment_id: UUID7, doctor_id: UUID7) -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id_with_lock(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()

        if not appointment.can_be_confirmed_by(doctor_id):
            raise UnauthorizedActionError("Only assigned doctor can confirm this appointment")

        if not appointment.can_transition_to(AppointmentStatus.CONFIRMED):
            raise InvalidStatusTransitionError("Appointment cannot be confirmed from current status")

        appointment.status = AppointmentStatus.CONFIRMED
        appointment.confirmed_at = utcnow()
        appointment.queue_number = await self.appointment_repo.get_next_queue_number(
            appointment.doctor_id,
            appointment.appointment_date,
        )
        await self.appointment_repo.save(appointment)

        await OutboxWriter.write(
            self.session,
            aggregate_id=appointment.id,
            aggregate_type="appointment_events",
            event_type="appointment.confirmed",
            payload={
                "appointment_id": str(appointment.id),
                "doctor_id": str(appointment.doctor_id),
                "patient_id": str(appointment.patient_id),
                "queue_number": appointment.queue_number,
            },
        )
        await OutboxWriter.write(
            self.session,
            aggregate_id=appointment.id,
            aggregate_type="cache_events",
            event_type="cache.invalidate",
            payload={
                "patterns": [
                    f"queue:{appointment.doctor_id}:{appointment.appointment_date}",
                ]
            },
        )
        return AppointmentResponse.model_validate(appointment)
