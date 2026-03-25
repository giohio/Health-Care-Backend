from abc import ABC, abstractmethod

from Domain.entities.notification import Notification
from uuid_extension import UUID7


class INotificationRepository(ABC):
    @abstractmethod
    async def save(self, notification: Notification) -> Notification:
        pass

    @abstractmethod
    async def get_by_id(self, notification_id: UUID7) -> Notification | None:
        pass

    @abstractmethod
    async def list_by_user(self, user_id: UUID7, limit: int = 50, offset: int = 0) -> list[Notification]:
        pass

    @abstractmethod
    async def mark_read(self, notification_id: UUID7) -> Notification | None:
        pass
