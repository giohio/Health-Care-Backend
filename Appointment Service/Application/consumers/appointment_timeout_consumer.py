import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from Application.use_cases._helpers import utcnow
from Domain.value_objects.appointment_status import AppointmentStatus
from healthai_db import OutboxWriter
from healthai_events import BaseConsumer
from healthai_events.exceptions import RetryableError
from infrastructure.database.models import AppointmentModel


class AppointmentTimeoutConsumer(BaseConsumer):
    """Cancel stale pending appointments when timeout checkpoint is reached."""

    QUEUE = "appointment.timeout_checker"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.check_timeout"

    def __init__(self, connection, cache, session_factory):
        super().__init__(connection, cache)
        self._session_factory = session_factory

    async def handle(self, payload: dict[str, Any]) -> None:
        appointment_id_raw = payload.get("appointment_id")
        timeout_at_raw = payload.get("timeout_at")

        if not appointment_id_raw:
            raise ValueError("Missing appointment_id in payload")

        appointment_id = uuid.UUID(str(appointment_id_raw))
        timeout_at = self._parse_timeout(timeout_at_raw)

        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(AppointmentModel)
                    .where(AppointmentModel.id == appointment_id)
                    .with_for_update()
                )
                appt = result.scalar_one_or_none()

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

    @staticmethod
    def _parse_timeout(raw: str | None) -> datetime | None:
        if not raw:
            return None
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
