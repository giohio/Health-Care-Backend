from Application.dtos import AppointmentResponse
from Application.use_cases._helpers import utcnow
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
    UnauthorizedActionError,
)
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from healthai_db import OutboxWriter
from uuid_extension import UUID7


class CancelAppointmentUseCase:
    def __init__(self, session, appointment_repo: IAppointmentRepository):
        self.session = session
        self.appointment_repo = appointment_repo

    async def execute(
        self,
        appointment_id: UUID7,
        actor_id: UUID7,
        actor_role: str,
        reason: str | None,
    ) -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id_with_lock(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()

        if not appointment.can_be_cancelled_by(actor_id, actor_role):
            raise UnauthorizedActionError("You are not allowed to cancel this appointment")

        if not appointment.can_transition_to(AppointmentStatus.CANCELLED):
            raise InvalidStatusTransitionError("Appointment cannot be cancelled from current status")

        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancelled_by = actor_role
        appointment.cancelled_by_user_id = actor_id
        appointment.cancelled_at = utcnow()
        appointment.cancel_reason = reason
        if appointment.payment_status == PaymentStatus.PAID:
            appointment.payment_status = PaymentStatus.REFUNDED
        await self.appointment_repo.save(appointment)

        await OutboxWriter.write(
            self.session,
            aggregate_id=appointment.id,
            aggregate_type="appointment_events",
            event_type="appointment.cancelled",
            payload={
                "appointment_id": str(appointment.id),
                "patient_id": str(appointment.patient_id),
                "doctor_id": str(appointment.doctor_id),
                "cancelled_by": actor_role,
                "cancelled_by_user_id": str(actor_id),
                "reason": reason,
            },
        )
        await OutboxWriter.write(
            self.session,
            aggregate_id=appointment.id,
            aggregate_type="cache_events",
            event_type="cache.invalidate",
            payload={
                "patterns": [
                    f"slots:{appointment.doctor_id}:{appointment.appointment_date}:*",
                    f"queue:{appointment.doctor_id}:{appointment.appointment_date}",
                ]
            },
        )
        if appointment.payment_status == PaymentStatus.REFUNDED:
            await OutboxWriter.write(
                self.session,
                aggregate_id=appointment.id,
                aggregate_type="payment_events",
                event_type="payment.refund_requested",
                payload={
                    "appointment_id": str(appointment.id),
                    "patient_id": str(appointment.patient_id),
                    "reason": reason or "appointment_cancelled",
                },
            )
        return AppointmentResponse.model_validate(appointment)
