import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from Application.use_cases._helpers import utcnow
from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from healthai_db import OutboxWriter
from healthai_events.consumer import BaseConsumer
from healthai_events.exceptions import RetryableError


class AppointmentTimeoutConsumer(BaseConsumer):
    """Cancel stale pending appointments when timeout checkpoint is reached."""

    QUEUE = "appointment.timeout_checker"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.check_timeout"

    def __init__(
        self,
        connection,
        cache,
        session_factory,
        appointment_repo_factory: Callable[[Any], IAppointmentRepository],
    ):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._appointment_repo_factory = appointment_repo_factory

    async def handle(self, payload: dict[str, Any]) -> None:
        appointment_id_raw = payload.get("appointment_id")
        timeout_at_raw = payload.get("timeout_at")

        if not appointment_id_raw:
            raise ValueError("Missing appointment_id in payload")

        appointment_id = uuid.UUID(str(appointment_id_raw))
        timeout_at = self._parse_timeout(timeout_at_raw)

        async with self._session_factory() as session:
            async with session.begin():
                repo = self._appointment_repo_factory(session)
                appt = await repo.get_by_id_with_lock(appointment_id)

                if not appt:
                    return
                if appt.status != AppointmentStatus.PENDING:
                    return

                now = datetime.now(timezone.utc)
                if timeout_at and now < timeout_at:
                    raise RetryableError("Timeout checkpoint fired too early")

                appt.status = AppointmentStatus.CANCELLED
                appt.cancel_reason = "timeout_no_confirmation"
                appt.cancelled_by = "system"
                appt.cancelled_at = utcnow()
                paid_before_timeout = appt.payment_status == PaymentStatus.PAID
                if paid_before_timeout:
                    appt.payment_status = PaymentStatus.REFUNDED

                await repo.save(appt)

                await OutboxWriter.write(
                    session,
                    aggregate_id=appt.id,
                    aggregate_type="appointment_events",
                    event_type="appointment.cancelled",
                    payload={
                        "appointment_id": str(appt.id),
                        "patient_id": str(appt.patient_id),
                        "doctor_id": str(appt.doctor_id),
                        "reason": "timeout_no_confirmation",
                        "cancelled_by": "system",
                    },
                )
                await OutboxWriter.write(
                    session,
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
                if paid_before_timeout:
                    await OutboxWriter.write(
                        session,
                        aggregate_id=appt.id,
                        aggregate_type="payment_events",
                        event_type="payment.refund_requested",
                        payload={
                            "appointment_id": str(appt.id),
                            "patient_id": str(appt.patient_id),
                            "reason": "timeout_no_confirmation",
                        },
                    )

    @staticmethod
    def _parse_timeout(raw: str | None) -> datetime | None:
        if not raw:
            return None
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
