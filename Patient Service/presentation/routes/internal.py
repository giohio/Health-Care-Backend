from fastapi import APIRouter, Depends, HTTPException
from typing import Annotated
from uuid import UUID
from Domain import IPatientProfileRepository, IPatientHealthRepository
from Application import GetProfileUseCase
from presentation.schema import PatientFullContextResponse
from presentation.dependencies import get_profile_repo, get_health_repo

router = APIRouter(prefix="/internal/patients", tags=["Internal"])


@router.get(
    "/{user_id}/full-context",
    response_model=PatientFullContextResponse,
    responses={404: {"description": "Patient not found"}}
)
async def get_patient_full_context_internal(
    user_id: UUID,
    profile_repo: Annotated[IPatientProfileRepository, Depends(get_profile_repo)],
    health_repo: Annotated[IPatientHealthRepository, Depends(get_health_repo)]
):
    """
    Internal API used by AI Agent or Auth Service to get full patient details.
    """
    use_case = GetProfileUseCase(profile_repo, health_repo)
    try:
        from uuid_extension import UUID7
        profile, health = await use_case.execute(UUID7(str(user_id)))
        return {"profile": profile, "health_background": health}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=f"Patient not found: {str(e)}")
