from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated
from uuid import UUID
from Domain import IPatientProfileRepository, IPatientHealthRepository, IEventPublisher
from Application import GetProfileUseCase, UpdateProfileUseCase, UpdateHealthBackgroundUseCase
from presentation.dependencies import (
    get_profile_repo,
    get_health_repo,
    get_event_publisher,
    get_current_user_id
)
from presentation.schema import (
    PatientFullContextResponse,
    ProfileUpdate,
    PatientProfileResponse,
    HealthUpdate,
    PatientHealthResponse
)

router = APIRouter(tags=["Patient Profile"])


@router.get(
    "/",
    response_model=PatientFullContextResponse,
    responses={404: {"description": "Profile not found"}}
)
async def get_my_full_profile(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    profile_repo: Annotated[IPatientProfileRepository, Depends(get_profile_repo)],
    health_repo: Annotated[IPatientHealthRepository, Depends(get_health_repo)]
):
    use_case = GetProfileUseCase(profile_repo, health_repo)
    try:
        profile, health = await use_case.execute(user_id)
        return {"profile": profile, "health_background": health}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/profile",
    response_model=PatientProfileResponse,
    responses={404: {"description": "Profile not found"}}
)
async def update_my_profile(
    data: ProfileUpdate,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    profile_repo: Annotated[IPatientProfileRepository, Depends(get_profile_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)]
):
    use_case = UpdateProfileUseCase(profile_repo, event_publisher)
    try:
        updated_profile = await use_case.execute(user_id, **data.model_dump(exclude_unset=True))
        return updated_profile
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/health",
    response_model=PatientHealthResponse,
    responses={404: {"description": "Profile or health record not found"}}
)
async def update_my_health(
    data: HealthUpdate,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    profile_repo: Annotated[IPatientProfileRepository, Depends(get_profile_repo)],
    health_repo: Annotated[IPatientHealthRepository, Depends(get_health_repo)]
):
    use_case = UpdateHealthBackgroundUseCase(profile_repo, health_repo)
    try:
        updated_health = await use_case.execute(user_id, **data.model_dump(exclude_unset=True))
        return updated_health
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
