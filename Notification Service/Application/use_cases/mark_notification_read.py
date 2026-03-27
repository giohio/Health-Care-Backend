from Application.dtos import NotificationResponse


class MarkNotificationReadUseCase:
    def __init__(self, repo, cache=None):
        self.repo = repo
        self.cache = cache

    async def execute(self, notification_id):
        notification = await self.repo.mark_read(notification_id)
        if not notification:
            return None
        response = NotificationResponse.model_validate(notification)
        if self.cache:
            await self.cache.delete(f"notif:unread:{response.user_id}")
        return response
