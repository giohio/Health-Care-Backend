from functools import lru_cache
from typing import Annotated

from Application.use_cases.create_notification import CreateNotificationUseCase
from Application.use_cases.list_notifications import ListNotificationsUseCase
from Application.use_cases.mark_notification_read import MarkNotificationReadUseCase
from Domain.interfaces.email_sender import IEmailSender
from Domain.interfaces.realtime_notifier import IRealtimeNotifier
from fastapi import Depends
from healthai_cache import CacheClient
from infrastructure.config import settings
from infrastructure.database.session import get_db
from infrastructure.email.email_sender import EmailSender
from infrastructure.repositories.notification_repository import NotificationRepository
from infrastructure.websocket.manager import NotificationConnectionManager, notification_ws_manager
from sqlalchemy.ext.asyncio import AsyncSession


@lru_cache()
def get_cache_client() -> CacheClient:
    return CacheClient.from_url(settings.REDIS_URL)


def get_ws_manager() -> NotificationConnectionManager:
    return notification_ws_manager


@lru_cache()
def get_email_sender() -> IEmailSender:
    return EmailSender()


def get_db_session(session: Annotated[AsyncSession, Depends(get_db)]) -> AsyncSession:
    return session


def get_notification_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return NotificationRepository(session)


def get_create_notification_use_case(
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
    ws_manager: Annotated[IRealtimeNotifier, Depends(get_ws_manager)],
    email_sender: Annotated[IEmailSender, Depends(get_email_sender)],
):
    return CreateNotificationUseCase(repo, ws_manager, email_sender)


def get_list_notifications_use_case(
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
):
    return ListNotificationsUseCase(repo)


def get_mark_notification_read_use_case(
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
):
    return MarkNotificationReadUseCase(repo)
