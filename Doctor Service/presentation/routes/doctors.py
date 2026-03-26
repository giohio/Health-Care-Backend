from typing import Annotated, List
from uuid import UUID

from Application.dtos import DoctorAutoConfirmSettingsRequest, DoctorAutoConfirmSettingsResponse, DoctorDTO
from Application.use_cases.register_doctor import RegisterDoctorUseCase
from Application.use_cases.search_available_doctors import SearchAvailableDoctorsUseCase
from Application.use_cases.set_auto_confirm_settings import SetAutoConfirmSettingsUseCase
from Application.use_cases.update_doctor_profile import UpdateDoctorProfileUseCase
from Domain.exceptions.domain_exceptions import DoctorNotFoundException
from Domain.interfaces.doctor_repository import IDoctorRepository
from fastapi import APIRouter, Depends, Header, HTTPException
from presentation.dependencies import (
    get_doctor_repo,
    get_register_doctor_use_case,
    get_search_available_doctors_use_case,
    get_set_auto_confirm_settings_use_case,
    get_update_doctor_profile_use_case,
)

router = APIRouter(tags=["Doctors"])


@router.get("/health")
async def doctor_health_check():
    return {"status": "healthy", "service": "doctor-service"}


@router.post("/", response_model=DoctorDTO, responses={403: {"description": "Admin only"}})
async def provision_doctor(
    dto: DoctorDTO,
    use_case: Annotated[RegisterDoctorUseCase, Depends(get_register_doctor_use_case)],
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    if x_user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    await use_case.execute(dto.user_id, dto.full_name)
    return dto


@router.put(
    "/me/auto-confirm",
    response_model=DoctorAutoConfirmSettingsResponse,
    responses={
        400: {"description": "Invalid auto-confirm configuration"},
        403: {"description": "Doctor only"},
        404: {"description": "Doctor not found"},
    },
)
async def set_my_auto_confirm_settings(
    payload: DoctorAutoConfirmSettingsRequest,
    use_case: Annotated[SetAutoConfirmSettingsUseCase, Depends(get_set_auto_confirm_settings_use_case)],
    x_user_id: UUID = Header(alias="X-User-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    if x_user_role != "doctor":
        raise HTTPException(status_code=403, detail="Doctor only")

    try:
        return await use_case.execute(
            doctor_id=x_user_id,
            auto_confirm=payload.auto_confirm,
            confirmation_timeout_minutes=payload.confirmation_timeout_minutes,
        )
    except DoctorNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{user_id}", response_model=DoctorDTO, responses={404: {"description": "Doctor not found"}})
async def get_doctor(user_id: UUID, repo: Annotated[IDoctorRepository, Depends(get_doctor_repo)]):
    doctor = await repo.get_by_id(user_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return DoctorDTO.model_validate(doctor)


@router.put(
    "/{user_id}",
    response_model=DoctorDTO,
    responses={400: {"description": "User ID mismatch"}, 404: {"description": "Doctor not found"}},
)
async def update_doctor(
    user_id: UUID,
    dto: DoctorDTO,
    use_case: Annotated[UpdateDoctorProfileUseCase, Depends(get_update_doctor_profile_use_case)],
):
    if user_id != dto.user_id:
        raise HTTPException(status_code=400, detail="User ID mismatch")
    try:
        return await use_case.execute(dto)
    except DoctorNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/specialty/{specialty_id}", response_model=List[DoctorDTO])
async def list_doctors_by_specialty(specialty_id: UUID, repo: Annotated[IDoctorRepository, Depends(get_doctor_repo)]):
    doctors = await repo.list_by_specialty(specialty_id)
    return [DoctorDTO.model_validate(d) for d in doctors]


@router.get(
    "/search/available", response_model=List[DoctorDTO], responses={400: {"description": "Invalid time format"}}
)
async def search_available_doctors(
    specialty_id: UUID,
    day: int | str,
    time: str,
    use_case: Annotated[SearchAvailableDoctorsUseCase, Depends(get_search_available_doctors_use_case)],
):
    try:
        from datetime import time as dt_time

        if isinstance(day, str):
            day_value = day.strip().upper()
            day_map = {
                "MONDAY": 0,
                "TUESDAY": 1,
                "WEDNESDAY": 2,
                "THURSDAY": 3,
                "FRIDAY": 4,
                "SATURDAY": 5,
                "SUNDAY": 6,
            }
            if day_value in day_map:
                day = day_map[day_value]
            else:
                day = int(day_value)

        time_slot = dt_time.fromisoformat(time)
        return await use_case.execute(specialty_id, day, time_slot)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid day/time format")
