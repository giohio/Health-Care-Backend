from abc import ABC, abstractmethod
from typing import Dict, Any

class IEventPublisher(ABC):
    @abstractmethod
    async def publish(self, exchange_name: str, routing_key: str, message: Dict[str, Any], delay_ms: int = 0):
        """Publishes an event to the message bus."""
        pass
