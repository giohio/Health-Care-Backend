from fastapi import APIRouter, Depends, HTTPException, Header
from typing import List
from uuid import UUID
from Application.dtos import DoctorDTO
from Application.use_cases.update_doctor_profile import UpdateDoctorProfileUseCase
from Application.use_cases.search_available_doctors import SearchAvailableDoctorsUseCase
from Application.use_cases.register_doctor import RegisterDoctorUseCase
from Domain.interfaces.doctor_repository import IDoctorRepository
from presentation.dependencies import (
    get_update_doctor_profile_use_case,
    get_doctor_repo,
    get_search_available_doctors_use_case,
    get_register_doctor_use_case,
)
from Domain.exceptions.domain_exceptions import DoctorNotFoundException
from datetime import time
from typing import Annotated

router = APIRouter(tags=["Doctors"])


@router.post("/", response_model=DoctorDTO)
async def provision_doctor(
    dto: DoctorDTO,
    use_case: Annotated[RegisterDoctorUseCase, Depends(get_register_doctor_use_case)],
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None
):
    if x_user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    await use_case.execute(dto.user_id, dto.full_name)
    return dto

@router.get("/{user_id}", response_model=DoctorDTO, responses={404: {"description": "Doctor not found"}})
async def get_doctor(
    user_id: UUID,
    repo: Annotated[IDoctorRepository, Depends(get_doctor_repo)]
):
    doctor = await repo.get_by_id(user_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return DoctorDTO.model_validate(doctor)

@router.put("/{user_id}", response_model=DoctorDTO, responses={
    400: {"description": "User ID mismatch"},
    404: {"description": "Doctor not found"}
})
async def update_doctor(
    user_id: UUID,
    dto: DoctorDTO,
    use_case: Annotated[UpdateDoctorProfileUseCase, Depends(get_update_doctor_profile_use_case)]
):
    if user_id != dto.user_id:
        raise HTTPException(status_code=400, detail="User ID mismatch")
    try:
        return await use_case.execute(dto)
    except DoctorNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/specialty/{specialty_id}", response_model=List[DoctorDTO])
async def list_doctors_by_specialty(
    specialty_id: UUID,
    repo: Annotated[IDoctorRepository, Depends(get_doctor_repo)]
):
    doctors = await repo.list_by_specialty(specialty_id)
    return [DoctorDTO.model_validate(d) for d in doctors]

@router.get("/search/available", response_model=List[DoctorDTO], responses={400: {"description": "Invalid time format"}})
async def search_available_doctors(
    specialty_id: UUID,
    day: int,
    time: str,
    use_case: Annotated[SearchAvailableDoctorsUseCase, Depends(get_search_available_doctors_use_case)]
):
    try:
        from datetime import time as dt_time
        time_slot = dt_time.fromisoformat(time)
        return await use_case.execute(specialty_id, day, time_slot)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")
