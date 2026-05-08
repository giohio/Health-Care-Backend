"""Thin wrapper around RabbitMQPublisher for EMR Result Service."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from healthai_events import RabbitMQPublisher


class EmrEventPublisher:
    """Publish domain events from the EMR Result Service.

    Wraps ``RabbitMQPublisher`` with a convenience method that
    serialises the payload and routes to the ``lab_order_events``
    exchange by default.
    """

    def __init__(self, publisher: RabbitMQPublisher) -> None:
        self._publisher = publisher

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        exchange: str = "lab_order_events",
        message_id: str | None = None,
    ) -> None:
        await self._publisher.publish(
            exchange=exchange,
            routing_key=event_type,
            payload=payload,
            message_id=message_id,
        )
