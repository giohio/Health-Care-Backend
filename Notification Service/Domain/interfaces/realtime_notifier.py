from abc import ABC, abstractmethod


class IRealtimeNotifier(ABC):
    @abstractmethod
    async def send_to_user(self, user_id: str, payload: dict) -> None:
        pass
