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
