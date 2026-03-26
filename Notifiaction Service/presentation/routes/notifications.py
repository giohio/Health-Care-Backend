from typing import Annotated
from uuid import UUID

from Application.dtos import NotificationListResponse, NotificationResponse
from Application.use_cases.get_unread_count import GetUnreadCountUseCase
from Application.use_cases.list_notifications import ListNotificationsUseCase
from Application.use_cases.mark_all_read import MarkAllReadUseCase
from Application.use_cases.mark_notification_read import MarkNotificationReadUseCase
from fastapi import APIRouter, Depends, Header, HTTPException
from presentation.dependencies import (
    get_list_notifications_use_case,
    get_mark_all_read_use_case,
    get_mark_notification_read_use_case,
    get_unread_count_use_case,
)

router = APIRouter(tags=["Notifications"])
MISSING_USER_ID_HEADER_ERROR = "X-User-Id header is missing"


@router.get("/me", response_model=NotificationListResponse)
async def list_my_notifications(
    use_case: Annotated[ListNotificationsUseCase, Depends(get_list_notifications_use_case)],
    x_user_id: UUID | None = Header(default=None, alias="X-User-Id"),
    limit: int = 50,
    offset: int = 0,
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail=MISSING_USER_ID_HEADER_ERROR)
    notifications = await use_case.execute(x_user_id, limit=limit, offset=offset)
    unread_count = sum(1 for n in notifications if not n.is_read)

    return {
        "notifications": notifications,
        "unread_count": unread_count,
    }


@router.put(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    responses={404: {"description": "Notification not found"}},
)
async def mark_as_read(
    notification_id: UUID,
    use_case: Annotated[MarkNotificationReadUseCase, Depends(get_mark_notification_read_use_case)],
):
    notification = await use_case.execute(notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


@router.get("/unread-count")
async def get_unread_count(
    use_case: Annotated[GetUnreadCountUseCase, Depends(get_unread_count_use_case)],
    x_user_id: UUID | None = Header(default=None, alias="X-User-Id"),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail=MISSING_USER_ID_HEADER_ERROR)
    count = await use_case.execute(x_user_id)
    return {"count": count}


@router.put("/read-all")
async def mark_all_as_read(
    use_case: Annotated[MarkAllReadUseCase, Depends(get_mark_all_read_use_case)],
    x_user_id: UUID | None = Header(default=None, alias="X-User-Id"),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail=MISSING_USER_ID_HEADER_ERROR)
    count = await use_case.execute(x_user_id)
    return {"updated": count}
