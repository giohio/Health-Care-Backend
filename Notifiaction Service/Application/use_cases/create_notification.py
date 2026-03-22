from datetime import datetime, timezone

from uuid_extension import uuid7

from Application.dtos import NotificationResponse
from Domain.entities.notification import Notification
from Domain.interfaces.notification_repository import INotificationRepository
from infrastructure.websocket.manager import NotificationConnectionManager


class CreateNotificationUseCase:
    def __init__(self, repo: INotificationRepository, ws_manager: NotificationConnectionManager):
        self.repo = repo
        self.ws_manager = ws_manager

    async def execute(self, user_id, title: str, body: str, event_type: str) -> NotificationResponse:
        notification = Notification(
            id=uuid7(),
            user_id=user_id,
            title=title,
            body=body,
            event_type=event_type,
            created_at=datetime.now(timezone.utc),
        )
        await self.repo.save(notification)
        response = NotificationResponse.model_validate(notification)
        await self.ws_manager.send_to_user(str(user_id), response.model_dump(mode="json"))
        return response
