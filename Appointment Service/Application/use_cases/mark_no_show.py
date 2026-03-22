from uuid_extension import UUID7

from healthai_db import OutboxWriter

from Application.dtos import AppointmentResponse
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    UnauthorizedActionError,
    InvalidStatusTransitionError,
)
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.value_objects.appointment_status import AppointmentStatus


class MarkNoShowUseCase:
    def __init__(self, session, appointment_repo: IAppointmentRepository):
        self.session = session
        self.appointment_repo = appointment_repo

    async def execute(self, appointment_id: UUID7, doctor_id: UUID7) -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id_with_lock(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()

        if appointment.doctor_id != doctor_id:
            raise UnauthorizedActionError("Only assigned doctor can mark no-show")

        if not appointment.can_transition_to(AppointmentStatus.NO_SHOW):
            raise InvalidStatusTransitionError("Appointment cannot be marked no-show from current status")

        appointment.status = AppointmentStatus.NO_SHOW
        await self.appointment_repo.save(appointment)

        await OutboxWriter.write(
            self.session,
            aggregate_id=appointment.id,
            aggregate_type="appointment_events",
            event_type="appointment.no_show",
            payload={
                "appointment_id": str(appointment.id),
                "patient_id": str(appointment.patient_id),
                "doctor_id": str(appointment.doctor_id),
            },
        )
        return AppointmentResponse.model_validate(appointment)
