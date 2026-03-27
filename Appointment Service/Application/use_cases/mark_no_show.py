from Application.dtos import AppointmentResponse
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
    UnauthorizedActionError,
)
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.interfaces.event_publisher import IEventPublisher
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from healthai_cache import CacheClient
from uuid_extension import UUID7


class MarkNoShowUseCase:
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

    async def execute(self, appointment_id: UUID7, doctor_id: UUID7) -> AppointmentResponse:
        appointment = await self.appointment_repo.get_by_id_with_lock(appointment_id)
        if not appointment:
            raise AppointmentNotFoundException()

        if appointment.doctor_id != doctor_id:
            raise UnauthorizedActionError("Only assigned doctor can mark no-show")

        if not appointment.can_transition_to(AppointmentStatus.NO_SHOW):
            raise InvalidStatusTransitionError("Appointment cannot be marked no-show from current status")

        appointment.status = AppointmentStatus.NO_SHOW
        if appointment.payment_status == PaymentStatus.PAID:
            appointment.payment_status = PaymentStatus.REFUNDED
        await self.appointment_repo.save(appointment)

        await self.event_publisher.publish(
            session=self.session,
            aggregate_id=appointment.id,
            aggregate_type="appointment_events",
            event_type="appointment.no_show",
            payload={
                "appointment_id": str(appointment.id),
                "patient_id": str(appointment.patient_id),
                "doctor_id": str(appointment.doctor_id),
            },
        )
        if appointment.payment_status == PaymentStatus.REFUNDED:
            await self.event_publisher.publish(
                session=self.session,
                aggregate_id=appointment.id,
                aggregate_type="payment_events",
                event_type="payment.refund_requested",
                payload={
                    "appointment_id": str(appointment.id),
                    "patient_id": str(appointment.patient_id),
                    "reason": "no_show_refund",
                },
            )
        await self.session.commit()
        if self.cache:
            await self.cache.delete_pattern(f"slots:{appointment.doctor_id}:{appointment.appointment_date}:*")
            await self.cache.delete(f"queue:{appointment.doctor_id}:{appointment.appointment_date}")
        return AppointmentResponse.model_validate(appointment)
