from typing import Any

from Domain.interfaces import IEventPublisher
from healthai_db import OutboxWriter


class OutboxEventPublisher(IEventPublisher):
    async def publish(
        self,
        session: Any,
        aggregate_id: Any,
        aggregate_type: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        await OutboxWriter.write(
            session,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            payload=payload,
        )
