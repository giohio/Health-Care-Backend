from typing import Annotated
from uuid import UUID

from Domain import IEventPublisher
from fastapi import Depends, Header, HTTPException, status
from infrastructure.database.session import get_db
from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
from infrastructure.repositories.repositories import PatientHealthRepository, PatientProfileRepository
from sqlalchemy.ext.asyncio import AsyncSession


def get_profile_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    return PatientProfileRepository(session)


def get_health_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    return PatientHealthRepository(session)


def get_event_publisher(session: Annotated[AsyncSession, Depends(get_db)]) -> IEventPublisher:
    return OutboxEventPublisher(session)


def get_current_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id", include_in_schema=False),
) -> UUID:
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


def get_vitals_repo(session: Annotated[AsyncSession, Depends(get_db)]):
    from infrastructure.repositories.vitals_repository import VitalsRepository

    return VitalsRepository(session)


def get_initialize_profile_use_case(
    profile_repo: Annotated[PatientProfileRepository, Depends(get_profile_repo)],
    health_repo: Annotated[PatientHealthRepository, Depends(get_health_repo)],
):
    from Application.use_cases.initialize_profile import InitializeProfileUseCase

    return InitializeProfileUseCase(profile_repo, health_repo)


def get_record_vitals_use_case(
    repo=Depends(get_vitals_repo),
    session: Annotated[AsyncSession, Depends(get_db)] = None,
    initialize_use_case=Depends(get_initialize_profile_use_case),
):
    from Application.use_cases.manage_vitals import RecordVitalsUseCase

    return RecordVitalsUseCase(repo, session, initialize_use_case)


def get_latest_vitals_use_case(
    repo=Depends(get_vitals_repo), initialize_use_case=Depends(get_initialize_profile_use_case)
):
    from Application.use_cases.manage_vitals import GetLatestVitalsUseCase

    return GetLatestVitalsUseCase(repo, initialize_use_case)


def get_vitals_history_use_case(
    repo=Depends(get_vitals_repo), initialize_use_case=Depends(get_initialize_profile_use_case)
):
    from Application.use_cases.manage_vitals import GetVitalsHistoryUseCase

    return GetVitalsHistoryUseCase(repo, initialize_use_case)
