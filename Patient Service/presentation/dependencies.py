from uuid import UUID
from typing import Annotated
from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from infrastructure.database.session import get_db
from infrastructure.repositories.repositories import PatientProfileRepository, PatientHealthRepository
from shared_lib.messaging import BasePublisher
from infrastructure.config import settings


def get_profile_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    return PatientProfileRepository(session)


def get_health_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    return PatientHealthRepository(session)


def get_event_publisher():
    return BasePublisher(settings.RABBITMQ_URL)


def get_current_user_id(x_user_id: Annotated[str | None, Header(alias="X-User-Id", include_in_schema=False)] = None) -> UUID:
    """Reads X-User-Id header set by Kong after JWT verification. No local JWT decoding needed."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token.",
        )
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity in token.",
        )
