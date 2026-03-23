from datetime import date, timedelta

from Application.dtos import AppointmentResponse, CreateAppointmentRequest
from Application.use_cases._helpers import add_minutes, utcnow
from Domain.entities.appointment import Appointment
from Domain.exceptions.domain_exceptions import SlotNotAvailableError
from Domain.value_objects.appointment_status import AppointmentStatus
from healthai_common import SagaOrchestrator
from healthai_db import OutboxWriter
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
    ]
    COMPENSATIONS = {
        "create_appointment": "cancel_appointment",
        "acquire_slot_lock": "release_slot_lock",
    }
    CONFIRMATION_TIMEOUT_MINUTES = 15

    def __init__(
        self,
        session,
        cache,
        lock_manager,
        appointment_repo,
        doctor_client,
    ):
        super().__init__(session, cache)
        self.lock_manager = lock_manager
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client

    async def execute_validate_input(self, ctx):
        if ctx["appointment_date"] < date.today():
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
        end_time = add_minutes(ctx["start_time"], ctx["type_config"]["duration_minutes"])
        ctx["end_time"] = end_time
        taken = await self.appointment_repo.is_slot_taken(
            doctor_id=ctx["doctor_id"],
            appointment_date=ctx["appointment_date"],
            start_time=ctx["start_time"],
            end_time=end_time,
        )
        if taken:
            raise SlotNotAvailableError("Slot is no longer available")

    async def execute_create_appointment(self, ctx):
        appt = Appointment(
            id=uuid7(),
            patient_id=ctx["patient_id"],
            doctor_id=ctx["doctor_id"],
            specialty_id=ctx["specialty_id"],
            appointment_date=ctx["appointment_date"],
            start_time=ctx["start_time"],
            end_time=ctx["end_time"],
            appointment_type=ctx["appointment_type"],
            chief_complaint=ctx.get("chief_complaint"),
            note_for_doctor=ctx.get("note_for_doctor"),
            status=AppointmentStatus.PENDING,
        )
        self.session.add(appt)
        await self.session.flush()
        ctx["appointment"] = appt
        return appt

    async def execute_write_outbox(self, ctx):
        appt = ctx["appointment"]
        timeout_at = utcnow() + timedelta(minutes=self.CONFIRMATION_TIMEOUT_MINUTES)

        await OutboxWriter.write(
            self.session,
            aggregate_id=appt.id,
            aggregate_type="appointment_events",
            event_type="appointment.created",
            payload={
                "appointment_id": str(appt.id),
                "patient_id": str(appt.patient_id),
                "doctor_id": str(appt.doctor_id),
                "appointment_date": str(appt.appointment_date),
                "start_time": str(appt.start_time),
                "appointment_type": appt.appointment_type,
                "chief_complaint": appt.chief_complaint,
            },
        )
        await OutboxWriter.write(
            self.session,
            aggregate_id=appt.id,
            aggregate_type="appointment_events",
            event_type="appointment.check_timeout",
            payload={
                "appointment_id": str(appt.id),
                "timeout_at": timeout_at.isoformat(),
            },
        )
        await OutboxWriter.write(
            self.session,
            aggregate_id=appt.id,
            aggregate_type="cache_events",
            event_type="cache.invalidate",
            payload={
                "patterns": [
                    f"slots:{appt.doctor_id}:{appt.appointment_date}:*",
                    f"queue:{appt.doctor_id}:{appt.appointment_date}",
                ]
            },
        )

    async def compensate_cancel_appointment(self, ctx):
        appt = ctx.get("appointment")
        if not appt:
            return
        appt.status = AppointmentStatus.CANCELLED
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
    ):
        self.session = session
        self.cache = cache
        self.lock_manager = lock_manager
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client

    async def execute(self, request: CreateAppointmentRequest) -> AppointmentResponse:
        saga = BookAppointmentSaga(
            session=self.session,
            cache=self.cache,
            lock_manager=self.lock_manager,
            appointment_repo=self.appointment_repo,
            doctor_client=self.doctor_client,
        )
        results = await saga.run(request.model_dump())
        appt = results.get("create_appointment")
        return AppointmentResponse.model_validate(appt)
