from Application.dtos import AppointmentResponse
from Application.use_cases._helpers import utcnow
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
    UnauthorizedActionError,
)
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.interfaces.event_publisher import IEventPublisher
from Domain.value_objects.appointment_status import AppointmentStatus
from uuid_extension import UUID7


class StartAppointmentUseCase:
    def __init__(self, session, appointment_repo: IAppointmentRepository, event_publisher: IEventPublisher):
        self.session = session
        self.appointment_repo = appointment_repo
        self.event_publisher = event_publisher

    async def execute(self, appointment_id: UUID7, doctor_id: UUID7) -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id_with_lock(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()

        if appointment.doctor_id != doctor_id:
            raise UnauthorizedActionError("Only assigned doctor can start this appointment")

        if not appointment.can_transition_to(AppointmentStatus.IN_PROGRESS):
            raise InvalidStatusTransitionError("Appointment cannot be started from current status")

        appointment.status = AppointmentStatus.IN_PROGRESS
        appointment.started_at = utcnow()
        await self.appointment_repo.save(appointment)

        await self.event_publisher.publish(
            session=self.session,
            aggregate_id=appointment.id,
            aggregate_type="appointment_events",
            event_type="appointment.started",
            payload={
                "appointment_id": str(appointment.id),
                "doctor_id": str(appointment.doctor_id),
                "patient_id": str(appointment.patient_id),
            },
        )
        await self.session.commit()
        return AppointmentResponse.model_validate(appointment)
