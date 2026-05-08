from Application.dtos import AppointmentResponse
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
)
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.interfaces.event_publisher import IEventPublisher
from Domain.value_objects.appointment_status import AppointmentStatus
from healthai_cache import CacheClient
from uuid_extension import UUID7


class MarkOverdueAppointmentUseCase:
    """
    System-initiated use case that marks a CONFIRMED appointment as OVERDUE
    when the scheduled end_time has passed without the appointment starting.

    Does NOT trigger a refund — the patient may still arrive late.
    Publishes an appointment.overdue event consumed by Notification Service.
    """

    def __init__(
        self,
        session,
        appointment_repo: IAppointmentRepository,
        event_publisher: IEventPublisher,
        cache: CacheClient | None = None,
    ):
        self.session = session
        self.appointment_repo = appointment_repo
        self.event_publisher = event_publisher
        self.cache = cache

    async def execute(self, appointment_id: UUID7, reason: str = "system_overdue") -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id_with_lock(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()

        if not appointment.can_transition_to(AppointmentStatus.OVERDUE):
            raise InvalidStatusTransitionError(
                f"Cannot mark appointment as overdue from status {appointment.status.value}"
            )

        appointment.status = AppointmentStatus.OVERDUE
        appointment.cancel_reason = reason
        await self.appointment_repo.save(appointment)

        await self.event_publisher.publish(
            session=self.session,
            aggregate_id=appointment.id,
            aggregate_type="appointment_events",
            event_type="appointment.overdue",
            payload={
                "appointment_id": str(appointment.id),
                "patient_id": str(appointment.patient_id),
                "doctor_id": str(appointment.doctor_id),
                "reason": reason,
            },
        )

        await self.session.commit()

        if self.cache:
            await self.cache.delete_pattern(f"slots:{appointment.doctor_id}:{appointment.appointment_date}:*")
            await self.cache.delete(f"queue:{appointment.doctor_id}:{appointment.appointment_date}")

        return AppointmentResponse.model_validate(appointment)
