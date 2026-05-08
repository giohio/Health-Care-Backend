import logging
from datetime import time
from typing import Annotated
from uuid import UUID

from Application.use_cases.get_system_config import GetSystemConfigUseCase
from Application.use_cases.get_notification_settings import GetNotificationSettingsUseCase
from Application.use_cases.get_security_settings import GetSecuritySettingsUseCase
from Application.use_cases.list_users import ListUsersUseCase
from Application.use_cases.update_user_profile import UpdateUserProfileUseCase
from Application.use_cases.update_user_status import UpdateUserStatusUseCase
from Application.use_cases.upsert_system_config import UpsertSystemConfigUseCase
from Application.use_cases.upsert_notification_settings import UpsertNotificationSettingsUseCase
from Application.use_cases.upsert_security_settings import UpsertSecuritySettingsUseCase
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from presentation.dependencies import (
    get_db,
    get_get_notification_settings_use_case,
    get_get_security_settings_use_case,
    get_get_system_config_use_case,
    get_list_users_use_case,
    get_upsert_notification_settings_use_case,
    get_upsert_security_settings_use_case,
    get_update_user_profile_use_case,
    get_update_user_status_use_case,
    get_upsert_system_config_use_case,
)
from presentation.schema import (
    NotificationSettingsUpdate,
    NotificationSettingsResponse,
    SecuritySettingsUpdate,
    SecuritySettingsResponse,
    SystemConfigUpdate,
    UserAdminUpdate,
    UserStatusUpdate,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin", tags=["Admin — Auth"])
logger = logging.getLogger(__name__)


def _require_admin(x_user_role: str | None = Header(default=None, alias="X-User-Role", include_in_schema=False)):
    if x_user_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


# ── System Config ─────────────────────────────────────────────────────────────

@router.get(
    "/config",
    summary="Get clinic system config",
)
async def get_config(
    use_case: Annotated[GetSystemConfigUseCase, Depends(get_get_system_config_use_case)],
    _: None = Depends(_require_admin),
):
    """Returns current system config. Returns hardcoded defaults when table is empty."""
    cfg = await use_case.execute()
    return {"status": "success", "data": cfg}


@router.put(
    "/config",
    summary="Update clinic system config (partial)",
)
async def update_config(
    body: SystemConfigUpdate,
    use_case: Annotated[UpsertSystemConfigUseCase, Depends(get_upsert_system_config_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_id: str | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
    _: None = Depends(_require_admin),
):
    fields = body.model_dump(exclude_none=True)

    # Convert HH:MM strings to time objects
    for key in ("working_hours_start", "working_hours_end"):
        if key in fields and isinstance(fields[key], str):
            try:
                h, m = fields[key].split(":")
                fields[key] = time(int(h), int(m))
            except (ValueError, AttributeError):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{key} must be in HH:MM format",
                )

    caller_id = UUID(x_user_id) if x_user_id else None
    try:
        cfg = await use_case.execute(updated_by=caller_id, **fields)
        await db.commit()
        return {"status": "success", "data": cfg}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


# ── User management ───────────────────────────────────────────────────────────

@router.get(
    "/users",
    summary="List users with filters and pagination",
)
async def list_users(
    use_case: Annotated[ListUsersUseCase, Depends(get_list_users_use_case)],
    role: str | None = Query(default=None, description="patient | doctor | admin"),
    search: str | None = Query(default=None, description="ILIKE search on email"),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _: None = Depends(_require_admin),
):
    result = await use_case.execute(
        role=role, search=search, is_active=is_active, page=page, limit=limit
    )
    return {"status": "success", "data": result}


@router.patch(
    "/users/{user_id}",
    summary="Update user profile fields",
)
async def update_user_profile(
    user_id: UUID,
    body: UserAdminUpdate,
    use_case: Annotated[UpdateUserProfileUseCase, Depends(get_update_user_profile_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_id: str | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
    _: None = Depends(_require_admin),
):
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated")

    caller_id = UUID(x_user_id)
    fields = body.model_dump(exclude_none=True)

    try:
        user = await use_case.execute(user_id=user_id, caller_id=caller_id, **fields)
        await db.commit()
        return {"status": "success", "data": user}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch(
    "/users/{user_id}/status",
    summary="Activate or deactivate a user",
)
async def update_user_status(
    user_id: UUID,
    body: UserStatusUpdate,
    use_case: Annotated[UpdateUserStatusUseCase, Depends(get_update_user_status_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_id: str | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
    _: None = Depends(_require_admin),
):
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthenticated")

    caller_id = UUID(x_user_id)
    try:
        user = await use_case.execute(user_id=user_id, is_active=body.is_active, caller_id=caller_id)
        await db.commit()
        return {"status": "success", "data": user}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ── Notification Settings ──────────────────────────────────────────────────────

@router.get(
    "/settings/notifications",
    response_model=NotificationSettingsResponse,
    summary="Get notification settings",
)
async def get_notification_settings(
    use_case: Annotated[GetNotificationSettingsUseCase, Depends(get_get_notification_settings_use_case)],
    _: None = Depends(_require_admin),
):
    """Returns notification settings. Returns null settings when table is empty."""
    return await use_case.execute()


@router.put(
    "/settings/notifications",
    response_model=NotificationSettingsResponse,
    summary="Update notification settings",
)
async def update_notification_settings(
    body: NotificationSettingsUpdate,
    use_case: Annotated[UpsertNotificationSettingsUseCase, Depends(get_upsert_notification_settings_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_id: str | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
    _: None = Depends(_require_admin),
):
    """Updates notification settings (replaces entire settings list)."""
    caller_id = UUID(x_user_id) if x_user_id else None
    cfg = await use_case.execute(settings=body.settings, updated_by=caller_id)
    await db.commit()
    return cfg


# ── Security Settings ────────────────────────────────────────────────────────

@router.get(
    "/settings/security",
    response_model=SecuritySettingsResponse,
    summary="Get security settings",
)
async def get_security_settings(
    use_case: Annotated[GetSecuritySettingsUseCase, Depends(get_get_security_settings_use_case)],
    _: None = Depends(_require_admin),
):
    """Returns security settings with defaults applied."""
    return await use_case.execute()


@router.put(
    "/settings/security",
    response_model=SecuritySettingsResponse,
    summary="Update security settings",
)
async def update_security_settings(
    body: SecuritySettingsUpdate,
    use_case: Annotated[UpsertSecuritySettingsUseCase, Depends(get_upsert_security_settings_use_case)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_id: str | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
    _: None = Depends(_require_admin),
):
    """Updates security settings (partial update)."""
    caller_id = UUID(x_user_id) if x_user_id else None
    fields = body.model_dump(exclude_none=True)

    # Validate session_timeout_minutes
    if "session_timeout_minutes" in fields:
        val = fields["session_timeout_minutes"]
        if not (5 <= val <= 480):
            raise HTTPException(status_code=422, detail="session_timeout_minutes must be between 5 and 480")

    # Validate login_attempt_limit
    if "login_attempt_limit" in fields:
        val = fields["login_attempt_limit"]
        if not (1 <= val <= 20):
            raise HTTPException(status_code=422, detail="login_attempt_limit must be between 1 and 20")

    cfg = await use_case.execute(updated_by=caller_id, **fields)
    await db.commit()
    return cfg
