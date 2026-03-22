from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from Application.use_cases.create_notification import CreateNotificationUseCase
from Application.use_cases.list_notifications import ListNotificationsUseCase
from Application.use_cases.mark_notification_read import MarkNotificationReadUseCase
from healthai_cache import CacheClient
from infrastructure.config import settings
from infrastructure.database.session import get_db
from infrastructure.repositories.notification_repository import NotificationRepository
from infrastructure.websocket.manager import NotificationConnectionManager


@lru_cache()
def get_cache_client() -> CacheClient:
    return CacheClient.from_url(settings.REDIS_URL)


@lru_cache()
def get_ws_manager() -> NotificationConnectionManager:
    return NotificationConnectionManager()


def get_db_session(session: Annotated[AsyncSession, Depends(get_db)]) -> AsyncSession:
    return session


def get_notification_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return NotificationRepository(session)


def get_create_notification_use_case(
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
    ws_manager: Annotated[NotificationConnectionManager, Depends(get_ws_manager)],
):
    return CreateNotificationUseCase(repo, ws_manager)


def get_list_notifications_use_case(
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
):
    return ListNotificationsUseCase(repo)


def get_mark_notification_read_use_case(
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
):
    return MarkNotificationReadUseCase(repo)
