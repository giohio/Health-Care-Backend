from typing import Annotated
from uuid import UUID

from Application import GetProfileUseCase, UpdateHealthBackgroundUseCase, UpdateProfileUseCase
from Application.use_cases.get_health_summary import GetHealthSummaryUseCase
from Application.use_cases.manage_vitals import GetLatestVitalsUseCase, GetVitalsHistoryUseCase, RecordVitalsUseCase
from Domain import IEventPublisher, IPatientHealthRepository, IPatientProfileRepository
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from presentation.dependencies import (
    get_current_user_id,
    get_event_publisher,
    get_health_repo,
    get_latest_vitals_use_case,
    get_profile_repo,
    get_record_vitals_use_case,
    get_vitals_history_use_case,
)
from presentation.schema import (
    HealthUpdate,
    PatientFullContextResponse,
    PatientHealthResponse,
    PatientProfileResponse,
    ProfileUpdate,
)

router = APIRouter(tags=["Patient Profile"])


@router.get("/", response_model=PatientFullContextResponse, responses={404: {"description": "Profile not found"}})
async def get_my_full_profile(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    profile_repo: Annotated[IPatientProfileRepository, Depends(get_profile_repo)],
    health_repo: Annotated[IPatientHealthRepository, Depends(get_health_repo)],
):
    use_case = GetProfileUseCase(profile_repo, health_repo)
    try:
        profile, health = await use_case.execute(user_id)
        return {"profile": profile, "health_background": health}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/profile", response_model=PatientProfileResponse, responses={404: {"description": "Profile not found"}})
async def update_my_profile(
    data: ProfileUpdate,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    profile_repo: Annotated[IPatientProfileRepository, Depends(get_profile_repo)],
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
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
    responses={404: {"description": "Profile or health record not found"}},
)
async def update_my_health(
    data: HealthUpdate,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    profile_repo: Annotated[IPatientProfileRepository, Depends(get_profile_repo)],
    health_repo: Annotated[IPatientHealthRepository, Depends(get_health_repo)],
):
    use_case = UpdateHealthBackgroundUseCase(profile_repo, health_repo)
    try:
        updated_health = await use_case.execute(user_id, **data.model_dump(exclude_unset=True))
        return updated_health
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/health-summary")
async def get_health_summary(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    profile_repo: Annotated[IPatientProfileRepository, Depends(get_profile_repo)],
    health_repo: Annotated[IPatientHealthRepository, Depends(get_health_repo)],
):
    use_case = GetHealthSummaryUseCase(profile_repo, health_repo)
    return await use_case.execute(user_id)


@router.post("/{patient_id}/vitals")
async def record_vitals(
    patient_id: UUID,
    x_user_id: Annotated[UUID, Depends(get_current_user_id)],
    use_case: Annotated[RecordVitalsUseCase, Depends(get_record_vitals_use_case)],
    height_cm: float | None = Query(default=None),
    weight_kg: float | None = Query(default=None),
    blood_pressure_systolic: int | None = Query(default=None),
    blood_pressure_diastolic: int | None = Query(default=None),
    heart_rate: int | None = Query(default=None),
    temperature_celsius: float | None = Query(default=None),
):
    vitals_data = {
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "blood_pressure_systolic": blood_pressure_systolic,
        "blood_pressure_diastolic": blood_pressure_diastolic,
        "heart_rate": heart_rate,
        "temperature_celsius": temperature_celsius,
    }
    # Filter out None values
    vitals_data = {k: v for k, v in vitals_data.items() if v is not None}
    result = await use_case.execute(patient_id, x_user_id, **vitals_data)
    return {
        "height_cm": result.height_cm,
        "weight_kg": result.weight_kg,
        "blood_pressure_systolic": result.blood_pressure_systolic,
        "blood_pressure_diastolic": result.blood_pressure_diastolic,
        "heart_rate": result.heart_rate,
        "temperature_celsius": result.temperature_celsius,
        "recorded_at": str(result.recorded_at),
    }


@router.get("/{patient_id}/vitals/latest")
async def get_latest_vitals(
    patient_id: UUID,
    use_case: Annotated[GetLatestVitalsUseCase, Depends(get_latest_vitals_use_case)],
    x_user_id: UUID | None = Header(default=None, alias="X-User-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    # Patients can only access their own vitals; doctors/admins can access any
    if x_user_role == "patient" and x_user_id != patient_id:
        raise HTTPException(status_code=403, detail="Access denied to other patient's vitals")
    vitals = await use_case.execute(patient_id)
    if not vitals:
        return None
    return {
        "vitals": {
            "height_cm": vitals.height_cm,
            "weight_kg": vitals.weight_kg,
            "blood_pressure_systolic": vitals.blood_pressure_systolic,
            "blood_pressure_diastolic": vitals.blood_pressure_diastolic,
            "heart_rate": vitals.heart_rate,
            "temperature_celsius": vitals.temperature_celsius,
            "recorded_at": str(vitals.recorded_at),
        }
    }


@router.get("/{patient_id}/vitals")
async def get_vitals_history(
    patient_id: UUID,
    use_case: Annotated[GetVitalsHistoryUseCase, Depends(get_vitals_history_use_case)],
    page: int = 1,
    limit: int = 20,
):
    vitals = await use_case.execute(patient_id, page, limit)
    return [
        {
            "id": str(v.id),
            "height_cm": v.height_cm,
            "weight_kg": v.weight_kg,
            "blood_pressure_systolic": v.blood_pressure_systolic,
            "blood_pressure_diastolic": v.blood_pressure_diastolic,
            "heart_rate": v.heart_rate,
            "temperature_celsius": v.temperature_celsius,
            "recorded_at": str(v.recorded_at),
        }
        for v in vitals
    ]
