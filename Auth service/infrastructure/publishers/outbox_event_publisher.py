import uuid
from typing import Any

from Domain.interfaces import IEventPublisher
from healthai_db import OutboxWriter


class OutboxEventPublisher(IEventPublisher):
    def __init__(self, session):
        self._session = session

    async def publish(self, exchange: str, routing_key: str, message: dict[str, Any], delay_ms: int = 0):
        del delay_ms

        raw_aggregate_id = message.get("user_id") or message.get("id")
        try:
            aggregate_id = uuid.UUID(str(raw_aggregate_id)) if raw_aggregate_id else uuid.uuid4()
        except (ValueError, TypeError):
            aggregate_id = uuid.uuid4()

        await OutboxWriter.write(
            self._session,
            aggregate_id=aggregate_id,
            aggregate_type=exchange,
            event_type=routing_key,
            payload=message,
        )
