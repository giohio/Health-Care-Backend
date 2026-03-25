from abc import ABC, abstractmethod
from typing import Any


class IEventPublisher(ABC):
    @abstractmethod
    async def publish(self, exchange: str, routing_key: str, message: dict[str, Any], delay_ms: int = 0):
        pass
