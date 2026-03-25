from abc import ABC, abstractmethod
from typing import Any


class IEventPublisher(ABC):
    @abstractmethod
    async def publish(
        self,
        session: Any,
        aggregate_id: Any,
        aggregate_type: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        raise NotImplementedError
