from Domain.interfaces.notification_repository import INotificationRepository


class GetUnreadCountUseCase:
    def __init__(self, repo: INotificationRepository):
        self.repo = repo

    async def execute(self, user_id) -> int:
        return await self.repo.count_unread(user_id)
