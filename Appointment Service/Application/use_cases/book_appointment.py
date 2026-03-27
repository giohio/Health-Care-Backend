from datetime import date, time
from uuid import UUID

from Application.dtos import AppointmentResponse, CreateAppointmentRequest
from Application.use_cases._helpers import add_minutes, utcnow
from Domain.entities.appointment import Appointment
from Domain.exceptions.domain_exceptions import SlotNotAvailableError
from Domain.interfaces.appointment_pricing import IAppointmentPricingPolicy
from Domain.interfaces.event_publisher import IEventPublisher
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from healthai_common import SagaOrchestrator
from healthai_events.exceptions import NonRetryableError
from uuid_extension import uuid7


class BookAppointmentSaga(SagaOrchestrator):
    """Distributed saga for booking appointments with lock + compensation."""

    SAGA_TYPE = "book_appointment"
    STEPS = [
        "validate_input",
        "acquire_slot_lock",
        "check_slot",
        "create_appointment",
        "write_outbox",
        "release_slot_lock",
    ]
    COMPENSATIONS = {
        "create_appointment": "cancel_appointment",
        "acquire_slot_lock": "release_slot_lock",
    }

    def __init__(
        self,
        session,
        cache,
        lock_manager,
        appointment_repo,
        doctor_client,
        event_publisher: IEventPublisher,
        pricing_policy: IAppointmentPricingPolicy,
    ):
        super().__init__(session, cache)
        self.lock_manager = lock_manager
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client
        self.event_publisher = event_publisher
        self.pricing_policy = pricing_policy

    @staticmethod
    def _as_uuid(value):
        return value if isinstance(value, UUID) else UUID(str(value))

    @staticmethod
    def _as_date(value):
        return value if isinstance(value, date) else date.fromisoformat(str(value))

    @staticmethod
    def _as_time(value):
        return value if isinstance(value, time) else time.fromisoformat(str(value))

    async def execute_validate_input(self, ctx):
        appointment_date = self._as_date(ctx["appointment_date"])
        if appointment_date < date.today():
            raise NonRetryableError("Cannot book an appointment in the past")

        config = await self.doctor_client.get_type_config(
            str(ctx["specialty_id"]),
            ctx["appointment_type"],
        )
        if not config:
            config = {"duration_minutes": 30, "buffer_minutes": 5}
        ctx["type_config"] = config

    async def execute_acquire_slot_lock(self, ctx):
        token = await self.lock_manager.acquire_slot(
            str(ctx["doctor_id"]),
            str(ctx["appointment_date"]),
            str(ctx["start_time"]),
        )
        if not token:
            raise SlotNotAvailableError("Slot is being booked by another request")
        ctx["lock_token"] = token

    async def execute_check_slot(self, ctx):
        doctor_id = self._as_uuid(ctx["doctor_id"])
        appointment_date = self._as_date(ctx["appointment_date"])
        start_time = self._as_time(ctx["start_time"])
        end_time = add_minutes(start_time, ctx["type_config"]["duration_minutes"])
        ctx["end_time"] = end_time.isoformat()
        taken = await self.appointment_repo.is_slot_taken(
            doctor_id=doctor_id,
            appointment_date=appointment_date,
            start_time=start_time,
            end_time=end_time,
        )
        if taken:
            raise SlotNotAvailableError("Slot is no longer available")

    async def execute_create_appointment(self, ctx):
        patient_id = self._as_uuid(ctx["patient_id"])
        doctor_id = self._as_uuid(ctx["doctor_id"])
        specialty_id = self._as_uuid(ctx["specialty_id"])
        appointment_date = self._as_date(ctx["appointment_date"])
        start_time = self._as_time(ctx["start_time"])
        end_time = self._as_time(ctx["end_time"])

        appt = Appointment(
            id=uuid7(),
            patient_id=patient_id,
            doctor_id=doctor_id,
            specialty_id=specialty_id,
            appointment_date=appointment_date,
            start_time=start_time,
            end_time=end_time,
            appointment_type=ctx["appointment_type"],
            chief_complaint=ctx.get("chief_complaint"),
            note_for_doctor=ctx.get("note_for_doctor"),
            status=AppointmentStatus.PENDING_PAYMENT,
            payment_status=PaymentStatus.PROCESSING,
        )
        await self.appointment_repo.save(appt)
        ctx["appointment_id"] = str(appt.id)
        return appt

    async def execute_write_outbox(self, ctx):
        appointment_id = self._as_uuid(ctx["appointment_id"])
        appt = await self.appointment_repo.get_by_id(appointment_id)
        if not appt:
            raise NonRetryableError("Appointment not found while writing outbox")

        cfg = ctx.get("type_config") or {}
        raw_amount = cfg.get("amount", cfg.get("price", self.pricing_policy.default_amount_vnd()))
        try:
            amount = int(raw_amount)
        except (TypeError, ValueError):
            amount = self.pricing_policy.default_amount_vnd()
        if amount <= 0:
            amount = self.pricing_policy.default_amount_vnd()

        await self.event_publisher.publish(
            session=self.session,
            aggregate_id=appt.id,
            aggregate_type="appointment_events",
            event_type="appointment.payment_required",
            payload={
                "appointment_id": str(appt.id),
                "patient_id": str(appt.patient_id),
                "doctor_id": str(appt.doctor_id),
                "appointment_date": str(appt.appointment_date),
                "start_time": str(appt.start_time),
                "end_time": str(appt.end_time),
                "appointment_type": appt.appointment_type,
                "chief_complaint": appt.chief_complaint,
                "amount": amount,
            },
        )
        if self.cache:
            await self.cache.delete_pattern(
                f"slots:{appt.doctor_id}:{appt.appointment_date}:*"
            )
            await self.cache.delete(f"queue:{appt.doctor_id}:{appt.appointment_date}")

    async def execute_release_slot_lock(self, ctx):
        token = ctx.get("lock_token")
        if not token:
            return
        await self.lock_manager.release_slot(
            str(ctx["doctor_id"]),
            str(ctx["appointment_date"]),
            str(ctx["start_time"]),
            token,
        )
        ctx["lock_token"] = None

    async def compensate_cancel_appointment(self, ctx):
        appointment_id = ctx.get("appointment_id")
        if not appointment_id:
            return
        appt = await self.appointment_repo.get_by_id(self._as_uuid(appointment_id))
        if not appt:
            return
        appt.status = AppointmentStatus.CANCELLED
        appt.payment_status = PaymentStatus.REFUNDED
        appt.cancel_reason = "saga_compensation"
        appt.cancelled_by = "system"
        appt.cancelled_at = utcnow()

    async def compensate_release_slot_lock(self, ctx):
        token = ctx.get("lock_token")
        if not token:
            return
        await self.lock_manager.release_slot(
            str(ctx["doctor_id"]),
            str(ctx["appointment_date"]),
            str(ctx["start_time"]),
            token,
        )


class BookAppointmentUseCase:
    def __init__(
        self,
        session,
        cache,
        lock_manager,
        appointment_repo,
        doctor_client,
        event_publisher: IEventPublisher,
        pricing_policy: IAppointmentPricingPolicy,
    ):
        self.session = session
        self.cache = cache
        self.lock_manager = lock_manager
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client
        self.event_publisher = event_publisher
        self.pricing_policy = pricing_policy

    async def execute(self, request: CreateAppointmentRequest) -> AppointmentResponse:
        saga = BookAppointmentSaga(
            session=self.session,
            cache=self.cache,
            lock_manager=self.lock_manager,
            appointment_repo=self.appointment_repo,
            doctor_client=self.doctor_client,
            event_publisher=self.event_publisher,
            pricing_policy=self.pricing_policy,
        )
        results = await saga.run(request.model_dump(mode="json"))
        await self.session.commit()
        appt = results.get("create_appointment")
        return AppointmentResponse.model_validate(appt)
