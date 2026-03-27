from Application.dtos import NotificationResponse
from Domain.interfaces.notification_repository import INotificationRepository


class ListNotificationsUseCase:
    def __init__(self, repo: INotificationRepository):
        self.repo = repo

    async def execute(self, user_id, limit: int = 50, offset: int = 0) -> list[NotificationResponse]:
        notifications = await self.repo.list_by_user(user_id, limit=limit, offset=offset)
        return [NotificationResponse.model_validate(item) for item in notifications]
