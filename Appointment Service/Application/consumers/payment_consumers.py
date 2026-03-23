from datetime import timedelta
from typing import Any
import uuid

from Application.use_cases._helpers import utcnow
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from healthai_db import OutboxWriter
from healthai_events import BaseConsumer
from infrastructure.clients.doctor_service_client import DoctorServiceClient
from infrastructure.database.models import AppointmentModel
from infrastructure.repositories.appointment_repository import AppointmentRepository
from sqlalchemy import func, select


class PaymentPaidConsumer(BaseConsumer):
    """Handle payment.paid and transition appointment by doctor auto-confirm config."""

    QUEUE = "appointment.payment_paid"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.paid"

    def __init__(self, connection, cache, session_factory):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._doctor_client = DoctorServiceClient(cache=cache)

    async def handle(self, payload: dict[str, Any]) -> None:
        appointment_id_raw = payload.get("appointment_id")
        if not appointment_id_raw:
            raise ValueError("Missing appointment_id in payment.paid payload")

        appointment_id = uuid.UUID(str(appointment_id_raw))

        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(AppointmentModel).where(AppointmentModel.id == appointment_id).with_for_update()
                )
                appt = result.scalar_one_or_none()
                if not appt:
                    return

                if appt.status != AppointmentStatus.PENDING_PAYMENT:
                    return

                appt.payment_status = PaymentStatus.PAID

                doctor_cfg = await self._doctor_client.get_doctor(str(appt.doctor_id))
                auto_confirm = True if doctor_cfg is None else doctor_cfg.get("auto_confirm", True)
                timeout_minutes = 15 if doctor_cfg is None else doctor_cfg.get("confirmation_timeout_minutes", 15)

                if auto_confirm:
                    queue_result = await session.execute(
                        select(func.count()).where(
                            AppointmentModel.doctor_id == appt.doctor_id,
                            AppointmentModel.appointment_date == appt.appointment_date,
                            AppointmentModel.status == AppointmentStatus.CONFIRMED,
                        )
                    )
                    appt.queue_number = (queue_result.scalar() or 0) + 1
                    appt.status = AppointmentStatus.CONFIRMED
                    appt.confirmed_at = utcnow()

                    await OutboxWriter.write(
                        session,
                        aggregate_id=appt.id,
                        aggregate_type="appointment_events",
                        event_type="appointment.auto_confirmed",
                        payload={
                            "appointment_id": str(appt.id),
                            "patient_id": str(appt.patient_id),
                            "doctor_id": str(appt.doctor_id),
                            "appointment_date": str(appt.appointment_date),
                            "start_time": str(appt.start_time),
                            "queue_number": appt.queue_number,
                            "auto_confirmed": True,
                        },
                    )
                    await OutboxWriter.write(
                        session,
                        aggregate_id=appt.id,
                        aggregate_type="appointment_events",
                        event_type="appointment.confirmed",
                        payload={
                            "appointment_id": str(appt.id),
                            "patient_id": str(appt.patient_id),
                            "doctor_id": str(appt.doctor_id),
                            "queue_number": appt.queue_number,
                            "auto_confirmed": True,
                        },
                    )
                    await OutboxWriter.write(
                        session,
                        aggregate_id=appt.id,
                        aggregate_type="appointment_events",
                        event_type="appointment.created",
                        payload={
                            "appointment_id": str(appt.id),
                            "doctor_id": str(appt.doctor_id),
                            "appointment_date": str(appt.appointment_date),
                            "start_time": str(appt.start_time),
                            "auto_confirmed": True,
                        },
                    )
                else:
                    appt.status = AppointmentStatus.PENDING
                    timeout_at = utcnow() + timedelta(minutes=int(timeout_minutes))

                    await OutboxWriter.write(
                        session,
                        aggregate_id=appt.id,
                        aggregate_type="appointment_events",
                        event_type="appointment.created",
                        payload={
                            "appointment_id": str(appt.id),
                            "doctor_id": str(appt.doctor_id),
                            "patient_id": str(appt.patient_id),
                            "appointment_date": str(appt.appointment_date),
                            "start_time": str(appt.start_time),
                            "auto_confirmed": False,
                        },
                    )
                    await OutboxWriter.write(
                        session,
                        aggregate_id=appt.id,
                        aggregate_type="appointment_events",
                        event_type="appointment.check_timeout",
                        payload={
                            "appointment_id": str(appt.id),
                            "timeout_at": timeout_at.isoformat(),
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


class PaymentFailedConsumer(BaseConsumer):
    QUEUE = "appointment.payment_failed"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.failed"

    def __init__(self, connection, cache, session_factory):
        super().__init__(connection, cache)
        self._session_factory = session_factory

    async def handle(self, payload: dict[str, Any]) -> None:
        await _cancel_for_payment(self._session_factory, payload, "payment_failed")


class PaymentExpiredConsumer(BaseConsumer):
    QUEUE = "appointment.payment_expired"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.expired"

    def __init__(self, connection, cache, session_factory):
        super().__init__(connection, cache)
        self._session_factory = session_factory

    async def handle(self, payload: dict[str, Any]) -> None:
        await _cancel_for_payment(self._session_factory, payload, "payment_expired")


class PaymentTimeoutConsumer(BaseConsumer):
    QUEUE = "appointment.payment_timeout"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.timeout"

    def __init__(self, connection, cache, session_factory):
        super().__init__(connection, cache)
        self._session_factory = session_factory

    async def handle(self, payload: dict[str, Any]) -> None:
        await _cancel_for_payment(self._session_factory, payload, "payment_timeout")


async def _cancel_for_payment(session_factory, payload: dict[str, Any], reason: str) -> None:
    appointment_id_raw = payload.get("appointment_id")
    if not appointment_id_raw:
        raise ValueError("Missing appointment_id in payment failure payload")

    appointment_id = uuid.UUID(str(appointment_id_raw))

    async with session_factory() as session:
        async with session.begin():
            repo = AppointmentRepository(session)
            appointment = await repo.get_by_id_with_lock(appointment_id)
            if not appointment:
                return

            if appointment.status != AppointmentStatus.PENDING_PAYMENT:
                return

            appointment.status = AppointmentStatus.CANCELLED
            appointment.payment_status = PaymentStatus.UNPAID
            appointment.cancelled_at = utcnow()
            appointment.cancelled_by = "system"
            appointment.cancel_reason = reason
            await repo.save(appointment)

            await OutboxWriter.write(
                session,
                aggregate_id=appointment.id,
                aggregate_type="appointment_events",
                event_type="appointment.cancelled",
                payload={
                    "appointment_id": str(appointment.id),
                    "patient_id": str(appointment.patient_id),
                    "doctor_id": str(appointment.doctor_id),
                    "reason": reason,
                    "cancelled_by": "system",
                },
            )
            await OutboxWriter.write(
                session,
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
