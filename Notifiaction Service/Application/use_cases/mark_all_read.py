from Domain.interfaces.notification_repository import INotificationRepository


class MarkAllReadUseCase:
    def __init__(self, repo: INotificationRepository):
        self.repo = repo

    async def execute(self, user_id) -> int:
        return await self.repo.mark_all_read(user_id)
