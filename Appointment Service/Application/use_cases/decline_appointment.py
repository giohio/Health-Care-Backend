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


class DeclineAppointmentUseCase:
    def __init__(self, session, appointment_repo: IAppointmentRepository):
        self.session = session
        self.appointment_repo = appointment_repo

    async def execute(self, appointment_id: UUID7, doctor_id: UUID7, reason: str | None) -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id_with_lock(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()

        if appointment.doctor_id != doctor_id:
            raise UnauthorizedActionError("Only assigned doctor can decline this appointment")

        if not appointment.can_transition_to(AppointmentStatus.DECLINED):
            raise InvalidStatusTransitionError("Appointment cannot be declined from current status")

        appointment.status = AppointmentStatus.DECLINED
        appointment.cancelled_by = "doctor"
        appointment.cancelled_by_user_id = doctor_id
        appointment.cancelled_at = utcnow()
        appointment.cancel_reason = reason
        await self.appointment_repo.save(appointment)

        await OutboxWriter.write(
            self.session,
            aggregate_id=appointment.id,
            aggregate_type="appointment_events",
            event_type="appointment.declined",
            payload={
                "appointment_id": str(appointment.id),
                "doctor_id": str(doctor_id),
                "patient_id": str(appointment.patient_id),
                "reason": reason,
            },
        )
        return AppointmentResponse.model_validate(appointment)
