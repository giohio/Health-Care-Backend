from Domain.interfaces.notification_repository import INotificationRepository

_UNREAD_TTL = 60


class GetUnreadCountUseCase:
    def __init__(self, repo: INotificationRepository, cache=None):
        self.repo = repo
        self.cache = cache

    async def execute(self, user_id) -> int:
        if self.cache:
            key = f"notif:unread:{user_id}"
            cached = await self.cache.get(key)
            if cached is not None:
                if isinstance(cached, str):
                    import json

                    cached = json.loads(cached)
                return int(cached)

        count = await self.repo.count_unread(user_id)
        if self.cache:
            await self.cache.setex(key, _UNREAD_TTL, count)
        return count
