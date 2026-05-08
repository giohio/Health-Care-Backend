"""
Event publisher for AI Service — publishes triage events to RabbitMQ.
Used to notify Notification Service when triage is completed.
"""
import logging
from typing import Any

import aio_pika
from aio_pika import Message, DeliveryMode

from infrastructure.config import get_settings

logger = logging.getLogger(__name__)


class TriageEventPublisher:
    """
    Publishes triage session events directly to RabbitMQ exchange.

    Unlike Appointment Service (which uses OutboxWriter + relay pattern),
    AI Service publishes directly since it doesn't need transactional
    consistency with entity changes — triage session is already saved
    before this is called.
    """

    EXCHANGE_NAME = "triage_events"

    def __init__(self):
        self._connection: aio_pika.Connection | None = None
        self._channel: aio_pika.Channel | None = None
        self._exchange: aio_pika.Exchange | None = None

    async def connect(self) -> None:
        if self._connection is not None:
            return
        settings = get_settings()
        try:
            self._connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            self._channel = await self._connection.channel()
            self._exchange = await self._channel.declare_exchange(
                self.EXCHANGE_NAME,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            logger.info("TriageEventPublisher connected to RabbitMQ")
        except Exception as e:
            logger.warning("TriageEventPublisher failed to connect: %s", e)
            self._connection = None

    async def publish(
        self,
        routing_key: str,
        payload: dict[str, Any],
    ) -> None:
        """Publish a triage event to the triage_events exchange."""
        if self._exchange is None:
            await self.connect()

        if self._exchange is None:
            logger.warning("Cannot publish triage event %s — not connected", routing_key)
            return

        message = Message(
            body=__import__("json").dumps(payload).encode(),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        )

        try:
            await self._exchange.publish(message, routing_key=routing_key)
            logger.info("Published triage event: %s", routing_key)
        except Exception as e:
            logger.error("Failed to publish triage event %s: %s", routing_key, e)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._exchange = None


# Singleton instance
_publisher: TriageEventPublisher | None = None


def get_triage_event_publisher() -> TriageEventPublisher:
    global _publisher
    if _publisher is None:
        _publisher = TriageEventPublisher()
    return _publisher
