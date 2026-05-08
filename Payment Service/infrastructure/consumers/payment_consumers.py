import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from Application.use_cases.create_payment import CreatePaymentFromEventUseCase
from Domain.interfaces import IEventPublisher, IPaymentProvider
from Domain.interfaces.payment_repository import IPaymentRepository
from Domain.value_objects.payment_status import PaymentStatus
from Domain.value_objects.payment_transaction_type import PaymentTransactionType
from healthai_events.consumer import BaseConsumer


class PaymentRequiredConsumer(BaseConsumer):
    """Create payment from appointment.payment_required event."""

    QUEUE = "payment.required"
    EXCHANGE = "appointment_events"
    ROUTING_KEY = "appointment.payment_required"

    def __init__(
        self,
        connection,
        cache,
        session_factory,
        payment_repo_factory: Callable[[Any], IPaymentRepository],
        payment_provider: IPaymentProvider,
        event_publisher: IEventPublisher,
    ):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._payment_repo_factory = payment_repo_factory
        self._payment_provider = payment_provider
        self._event_publisher = event_publisher

    async def handle(self, payload: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._payment_repo_factory(session)
                use_case = CreatePaymentFromEventUseCase(
                    session=session,
                    payment_repo=repo,
                    payment_provider=self._payment_provider,
                    event_publisher=self._event_publisher,
                )
                await use_case.execute(payload)


class PaymentExpiryConsumer(BaseConsumer):
    """Check and mark expired payments."""

    QUEUE = "payment.expiry_check"
    EXCHANGE = "payment_events"
    ROUTING_KEY = "payment.check_expiry"

    def __init__(
        self,
        connection,
        cache,
        session_factory,
        payment_repo_factory: Callable[[Any], IPaymentRepository],
        event_publisher: IEventPublisher,
    ):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._payment_repo_factory = payment_repo_factory
        self._event_publisher = event_publisher

    async def handle(self, payload: dict[str, Any]) -> None:
        payment_id = uuid.UUID(str(payload.get("payment_id")))
        appointment_id = uuid.UUID(str(payload.get("appointment_id")))

        async with self._session_factory() as session:
            async with session.begin():
                repo = self._payment_repo_factory(session)
                payment = await repo.get_by_id(payment_id)
                if not payment:
                    return
                if payment.status != PaymentStatus.PENDING:
                    return
                if not payment.is_expired(datetime.now(timezone.utc)):
                    return

                payment.mark_as_expired()
                await repo.save(payment)
                await repo.append_transaction(
                    payment_id=payment.id,
                    appointment_id=payment.appointment_id,
                    transaction_type=PaymentTransactionType.PAYMENT_EXPIRED,
                    amount=payment.amount,
                    currency=payment.currency,
                    metadata={
                        "source_event": "payment.check_expiry",
                    },
                )

                await self._event_publisher.publish(
                    session=session,
                    aggregate_id=payment.id,
                    aggregate_type="payment_events",
                    event_type="payment.expired",
                    payload={
                        "payment_id": str(payment.id),
                        "appointment_id": str(appointment_id),
                        "patient_id": str(payment.patient_id),
                        "doctor_id": str(payment.doctor_id),
                    },
                )


class PaymentRefundRequestedConsumer(BaseConsumer):
    """Handle refund requests."""

    REFUND_REQUESTED_EVENT = "payment.refund_requested"
    QUEUE = "payment.refund_requested"
    EXCHANGE = "payment_events"
    ROUTING_KEY = REFUND_REQUESTED_EVENT

    def __init__(
        self,
        connection,
        cache,
        session_factory,
        payment_repo_factory: Callable[[Any], IPaymentRepository],
        event_publisher: IEventPublisher,
    ):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._payment_repo_factory = payment_repo_factory
        self._event_publisher = event_publisher

    async def handle(self, payload: dict[str, Any]) -> None:
        payment_id_raw = payload.get("payment_id")
        appointment_id_raw = payload.get("appointment_id")
        payment_id = uuid.UUID(str(payment_id_raw)) if payment_id_raw else None
        appointment_id = uuid.UUID(str(appointment_id_raw)) if appointment_id_raw else None

        async with self._session_factory() as session:
            async with session.begin():
                repo = self._payment_repo_factory(session)
                payment = await repo.get_by_id(payment_id) if payment_id else None
                if not payment and appointment_id:
                    payment = await repo.get_by_appointment_id(appointment_id)
                if not payment:
                    return
                if payment.status != PaymentStatus.PAID:
                    return

                await repo.append_transaction(
                    payment_id=payment.id,
                    appointment_id=payment.appointment_id,
                    transaction_type=PaymentTransactionType.REFUND_REQUESTED,
                    amount=payment.amount,
                    currency=payment.currency,
                    metadata={
                        "source_event": self.REFUND_REQUESTED_EVENT,
                        "payload": payload,
                    },
                )

                payment.mark_as_refunded()
                await repo.save(payment)
                await repo.append_transaction(
                    payment_id=payment.id,
                    appointment_id=payment.appointment_id,
                    transaction_type=PaymentTransactionType.PAYMENT_REFUNDED,
                    amount=payment.amount,
                    currency=payment.currency,
                    metadata={
                        "source_event": self.REFUND_REQUESTED_EVENT,
                        "payload": payload,
                    },
                )

                await self._event_publisher.publish(
                    session=session,
                    aggregate_id=payment.id,
                    aggregate_type="payment_events",
                    event_type="payment.refunded",
                    payload={
                        "payment_id": str(payment.id),
                        "appointment_id": str(payment.appointment_id),
                        "patient_id": str(payment.patient_id),
                    },
                )


# ---------------------------------------------------------------------------
#  Appointment status cache sync consumers
# ---------------------------------------------------------------------------
#
#  Pattern: one consumer class per routing key (aligned with Notification Service).
#  A factory creates all 7 consumer classes and their instances in bulk.
#  Each consumer mirrors appointment state onto the payment record so that
#  history endpoints can surface appointment_status without a cross-service
#  HTTP call at query time.
# ---------------------------------------------------------------------------

def _appt_status_consumer_class(routing_key_suffix: str, new_status: str):
    """
    Class factory that returns a BaseConsumer subclass for one appointment event.

    routing_key_suffix: e.g. "confirmed" → ROUTING_KEY = "appointment.confirmed"
    new_status: value written to payments.appointment_status
    """

    class _Consumer(BaseConsumer):
        QUEUE = f"payment.appt_status.{routing_key_suffix}"
        EXCHANGE = "appointment_events"
        ROUTING_KEY = f"appointment.{routing_key_suffix}"
        _new_status = new_status

        def __init__(self, connection, cache, session_factory, payment_repo_factory):
            super().__init__(connection, cache)
            self._session_factory = session_factory
            self._payment_repo_factory = payment_repo_factory

        async def handle(self, payload: dict[str, Any]) -> None:
            raw_id = payload.get("appointment_id")
            if not raw_id:
                return
            appointment_id = uuid.UUID(str(raw_id))
            async with self._session_factory() as session:
                async with session.begin():
                    repo = self._payment_repo_factory(session)
                    await repo.update_appointment_status(appointment_id, self._new_status)

    _Consumer.__name__ = f"AppointmentStatusConsumer_{routing_key_suffix}"
    _Consumer.__qualname__ = _Consumer.__name__
    return _Consumer


# Concrete consumer classes (one per appointment event type)
_APPT_STATUS_EVENTS: list[tuple[str, str]] = [
    ("confirmed",   "confirmed"),
    ("cancelled",   "cancelled"),
    ("declined",    "declined"),
    ("completed",   "completed"),
    ("started",     "in_progress"),
    ("no_show",     "no_show"),
    ("rescheduled", "rescheduled"),
]

_APPT_STATUS_CONSUMER_CLASSES = [
    _appt_status_consumer_class(suffix, status)
    for suffix, status in _APPT_STATUS_EVENTS
]


def create_appointment_status_consumers(
    connection,
    cache,
    session_factory,
    payment_repo_factory: Callable[[Any], IPaymentRepository],
) -> list[BaseConsumer]:
    """Instantiate and return all appointment-status cache sync consumers."""
    return [
        cls(connection, cache, session_factory, payment_repo_factory)
        for cls in _APPT_STATUS_CONSUMER_CLASSES
    ]


class LabOrderPaymentRequiredConsumer(BaseConsumer):
    """Create lab order payment from lab_order.payment_required event."""

    QUEUE = "payment.lab_order_required"
    EXCHANGE = "lab_order_events"
    ROUTING_KEY = "lab_order.payment_required"

    def __init__(
        self,
        connection,
        cache,
        session_factory,
        payment_repo_factory: Callable[[Any], IPaymentRepository],
        payment_provider: IPaymentProvider,
        event_publisher: IEventPublisher,
    ):
        super().__init__(connection, cache)
        self._session_factory = session_factory
        self._payment_repo_factory = payment_repo_factory
        self._payment_provider = payment_provider
        self._event_publisher = event_publisher

    async def handle(self, payload: dict[str, Any]) -> None:
        from Application.use_cases.create_lab_order_payment import CreateLabOrderPaymentUseCase

        async with self._session_factory() as session:
            async with session.begin():
                repo = self._payment_repo_factory(session)
                use_case = CreateLabOrderPaymentUseCase(
                    session=session,
                    payment_repo=repo,
                    payment_provider=self._payment_provider,
                    event_publisher=self._event_publisher,
                )
                await use_case.execute(payload)
