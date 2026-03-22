from Application.dtos import NotificationResponse


class MarkNotificationReadUseCase:
    def __init__(self, repo):
        self.repo = repo

    async def execute(self, notification_id):
        notification = await self.repo.mark_read(notification_id)
        if not notification:
            return None
        return NotificationResponse.model_validate(notification)
