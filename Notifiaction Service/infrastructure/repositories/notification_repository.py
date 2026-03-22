from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extension import UUID7

from Domain.entities.notification import Notification
from Domain.interfaces.notification_repository import INotificationRepository
from infrastructure.database.models import NotificationModel


class NotificationRepository(INotificationRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, notification: Notification) -> Notification:
        model = NotificationModel(
            id=uuid.UUID(str(notification.id)),
            user_id=uuid.UUID(str(notification.user_id)),
            title=notification.title,
            body=notification.body,
            event_type=notification.event_type,
            is_read=notification.is_read,
            created_at=notification.created_at or datetime.now(timezone.utc),
            read_at=notification.read_at,
        )
        await self.session.merge(model)
        return notification

    async def get_by_id(self, notification_id: UUID7) -> Notification | None:
        result = await self.session.execute(
            select(NotificationModel).where(NotificationModel.id == uuid.UUID(str(notification_id)))
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_user(self, user_id: UUID7, limit: int = 50, offset: int = 0) -> list[Notification]:
        result = await self.session.execute(
            select(NotificationModel)
            .where(NotificationModel.user_id == uuid.UUID(str(user_id)))
            .order_by(NotificationModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    async def mark_read(self, notification_id: UUID7) -> Notification | None:
        result = await self.session.execute(
            select(NotificationModel)
            .where(NotificationModel.id == uuid.UUID(str(notification_id)))
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        if not model:
            return None

        model.is_read = True
        model.read_at = datetime.now(timezone.utc)
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: NotificationModel) -> Notification:
        return Notification(
            id=UUID7(str(model.id)),
            user_id=UUID7(str(model.user_id)),
            title=model.title,
            body=model.body,
            event_type=model.event_type,
            is_read=model.is_read,
            created_at=model.created_at,
            read_at=model.read_at,
        )
