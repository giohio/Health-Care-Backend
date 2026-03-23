from typing import Annotated
from uuid import UUID

from Application.dtos import NotificationResponse
from Application.use_cases.list_notifications import ListNotificationsUseCase
from Application.use_cases.mark_notification_read import MarkNotificationReadUseCase
from fastapi import APIRouter, Depends, Header, HTTPException
from presentation.dependencies import get_list_notifications_use_case, get_mark_notification_read_use_case

router = APIRouter(tags=["Notifications"])


@router.get("/me", response_model=list[NotificationResponse])
async def list_my_notifications(
    use_case: Annotated[ListNotificationsUseCase, Depends(get_list_notifications_use_case)],
    x_user_id: Annotated[UUID, Header(alias="X-User-Id")],
    limit: int = 50,
    offset: int = 0,
):
    return await use_case.execute(x_user_id, limit=limit, offset=offset)


@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: UUID,
    use_case: Annotated[MarkNotificationReadUseCase, Depends(get_mark_notification_read_use_case)],
):
    notification = await use_case.execute(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification
