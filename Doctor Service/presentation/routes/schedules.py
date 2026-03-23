from typing import Annotated, List
from uuid import UUID

from Application.dtos import ScheduleDTO
from Application.use_cases.update_schedule import UpdateScheduleUseCase
from Domain.exceptions.domain_exceptions import DoctorNotFoundException
from Domain.interfaces.schedule_repository import IScheduleRepository
from fastapi import APIRouter, Depends, HTTPException
from presentation.dependencies import get_schedule_repo, get_update_schedule_use_case

router = APIRouter(prefix="/{doctor_id}/schedule", tags=["Schedules"])


@router.get("", response_model=List[ScheduleDTO])
async def get_schedule(doctor_id: UUID, repo: Annotated[IScheduleRepository, Depends(get_schedule_repo)]):
    schedules = await repo.list_by_doctor(doctor_id)
    return [ScheduleDTO.model_validate(s) for s in schedules]


@router.put("", response_model=List[ScheduleDTO], responses={404: {"description": "Doctor not found"}})
async def update_schedule(
    doctor_id: UUID,
    dtos: List[ScheduleDTO],
    use_case: Annotated[UpdateScheduleUseCase, Depends(get_update_schedule_use_case)],
):
    try:
        return await use_case.execute(doctor_id, dtos)
    except DoctorNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
