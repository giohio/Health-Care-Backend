import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from Domain.value_objects.appointment_status import AppointmentStatus
from infrastructure.database.models import AppointmentModel


class AppointmentTimeoutHandler:
    """Handle appointment.check_timeout events and cancel stale pending bookings."""

    def __init__(self, session_factory, event_publisher):
        self._session_factory = session_factory
        self._event_publisher = event_publisher

    async def handle(self, payload: dict[str, Any]) -> None:
        appointment_id_raw = payload.get("appointment_id")
        timeout_at_raw = payload.get("timeout_at")

        if not appointment_id_raw:
            # Fatal payload issue -> reject to DLQ via shared consumer behavior.
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
                    # Transient timing issue -> requeue.
                    raise RuntimeError("Timeout checkpoint fired too early")

                appt.status = AppointmentStatus.CANCELLED

        await self._event_publisher.publish(
            exchange_name="appointment_events",
            routing_key="appointment.cancelled",
            message={
                "appointment_id": str(appointment_id),
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
