from datetime import datetime, timezone

from Application.dtos import NotificationResponse
from Domain.entities.notification import Notification
from Domain.interfaces.email_sender import IEmailSender
from Domain.interfaces.notification_repository import INotificationRepository
from Domain.interfaces.realtime_notifier import IRealtimeNotifier
from uuid_extension import uuid7
from uuid import UUID


class CreateNotificationUseCase:
    def __init__(
        self,
        repo: INotificationRepository,
        ws_manager: IRealtimeNotifier,
        email_sender: IEmailSender | None = None,
    ):
        self.repo = repo
        self.ws_manager = ws_manager
        self.email_sender = email_sender

    async def execute(
        self,
        user_id,
        title: str,
        body: str,
        event_type: str,
        recipient_email: str | None = None,
    ) -> NotificationResponse:
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
        ws_payload = response.model_dump(mode="json")
        message = {
            "event": "notification.new",
            "data": ws_payload,
        }

        raw_user_id = str(user_id)
        await self.ws_manager.send_to_user(raw_user_id, message)

        try:
            canonical_user_id = str(UUID(raw_user_id))
            if canonical_user_id != raw_user_id:
                await self.ws_manager.send_to_user(canonical_user_id, message)
        except Exception:
            pass
        if self.email_sender and recipient_email:
            await self.email_sender.send_email(
                to=recipient_email,
                subject=title,
                body=body,
            )
        return response
