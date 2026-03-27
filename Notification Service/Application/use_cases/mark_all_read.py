from Domain.interfaces.notification_repository import INotificationRepository


class MarkAllReadUseCase:
    def __init__(self, repo: INotificationRepository, cache=None):
        self.repo = repo
        self.cache = cache

    async def execute(self, user_id) -> int:
        count = await self.repo.mark_all_read(user_id)
        if self.cache:
            await self.cache.delete(f"notif:unread:{user_id}")
        return count
