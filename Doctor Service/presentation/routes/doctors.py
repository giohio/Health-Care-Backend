from typing import Annotated, List
from uuid import UUID

from Application.dtos import DoctorAutoConfirmSettingsRequest, DoctorAutoConfirmSettingsResponse, DoctorDTO
from Application.use_cases.get_availability import GetAvailabilityUseCase
from Application.use_cases.get_enhanced_schedule import GetEnhancedScheduleUseCase
from Application.use_cases.list_ratings import ListRatingsUseCase
from Application.use_cases.manage_day_off import AddDayOffUseCase, RemoveDayOffUseCase
from Application.use_cases.manage_service_offerings import (
    AddServiceOfferingUseCase,
    DeactivateServiceOfferingUseCase,
    ListServiceOfferingsUseCase,
    UpdateServiceOfferingUseCase,
)
from Application.use_cases.register_doctor import RegisterDoctorUseCase
from Application.use_cases.search_available_doctors import SearchAvailableDoctorsUseCase
from Application.use_cases.set_auto_confirm_settings import SetAutoConfirmSettingsUseCase
from Application.use_cases.set_availability import SetAvailabilityUseCase
from Application.use_cases.submit_rating import SubmitRatingUseCase
from Application.use_cases.update_doctor_profile import UpdateDoctorProfileUseCase
from Domain.exceptions.domain_exceptions import DoctorNotFoundException
from Domain.interfaces.doctor_repository import IDoctorRepository
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from presentation.dependencies import (
    get_add_day_off_use_case,
    get_add_service_offering_use_case,
    get_deactivate_service_offering_use_case,
    get_doctor_repo,
    get_enhanced_schedule_use_case,
    get_get_availability_use_case,
    get_list_ratings_use_case,
    get_list_service_offerings_use_case,
    get_register_doctor_use_case,
    get_remove_day_off_use_case,
    get_search_available_doctors_use_case,
    get_set_auto_confirm_settings_use_case,
    get_set_availability_use_case,
    get_submit_rating_use_case,
    get_update_doctor_profile_use_case,
    get_update_service_offering_use_case,
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
    x_user_id: UUID | None = Header(default=None, alias="X-User-Id"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header is missing")
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


@router.post("/{doctor_id}/ratings")
async def submit_rating(
    doctor_id: UUID,
    rating: int = Query(...),
    appointment_id: UUID | None = Query(default=None),
    comment: str | None = Query(default=None),
    use_case: Annotated[SubmitRatingUseCase, Depends(get_submit_rating_use_case)] = None,
    x_user_id: UUID | None = Header(default=None, alias="X-User-Id"),
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header is missing")
    try:
        result = await use_case.execute(doctor_id, x_user_id, rating, comment, appointment_id=appointment_id)
        return {"success": True, "rating_id": str(result.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{doctor_id}/ratings")
async def list_ratings(
    doctor_id: UUID,
    use_case: Annotated[ListRatingsUseCase, Depends(get_list_ratings_use_case)],
    page: int = 1,
    limit: int = 20,
):
    ratings = await use_case.execute(doctor_id, page, limit)
    return {"ratings": [{"rating": r.rating, "comment": r.comment, "created_at": str(r.created_at)} for r in ratings]}


@router.post("/{doctor_id}/availability")
async def set_availability(
    doctor_id: UUID,
    day_of_week: int,
    start_time: str,
    end_time: str,
    use_case: Annotated[SetAvailabilityUseCase, Depends(get_set_availability_use_case)],
    break_start: str | None = None,
    break_end: str | None = None,
    max_patients: int = 20,
):
    from datetime import time

    await use_case.execute(
        doctor_id,
        day_of_week,
        time.fromisoformat(start_time),
        time.fromisoformat(end_time),
        time.fromisoformat(break_start) if break_start else None,
        time.fromisoformat(break_end) if break_end else None,
        max_patients,
    )
    return {"success": True}


@router.get("/{doctor_id}/availability")
async def get_availability(
    doctor_id: UUID,
    use_case: Annotated[GetAvailabilityUseCase, Depends(get_get_availability_use_case)],
):
    availability = await use_case.execute(doctor_id)
    return {
        "items": [
            {
                "day_of_week": int(a.day_of_week),
                "start_time": str(a.start_time),
                "end_time": str(a.end_time),
                "max_patients": getattr(a, "max_patients", None),
                "break_start": str(a.break_start) if getattr(a, "break_start", None) else None,
                "break_end": str(a.break_end) if getattr(a, "break_end", None) else None,
            }
            for a in availability
        ]
    }


@router.post("/{doctor_id}/days-off")
async def add_day_off(
    doctor_id: UUID,
    off_date: str,
    use_case: Annotated[AddDayOffUseCase, Depends(get_add_day_off_use_case)],
    reason: str | None = None,
):
    from datetime import date

    await use_case.execute(doctor_id, date.fromisoformat(off_date), reason)
    return {"success": True}


@router.delete("/{doctor_id}/days-off/{off_date}")
async def remove_day_off(
    doctor_id: UUID,
    off_date: str,
    use_case: Annotated[RemoveDayOffUseCase, Depends(get_remove_day_off_use_case)],
):
    from datetime import date

    await use_case.execute(doctor_id, date.fromisoformat(off_date))
    return {"success": True}


@router.get("/{doctor_id}/services")
async def list_services(
    doctor_id: UUID,
    use_case: Annotated[ListServiceOfferingsUseCase, Depends(get_list_service_offerings_use_case)],
):
    services = await use_case.execute(doctor_id)
    return {
        "services": [
            {"id": str(s.id), "name": s.service_name, "fee": s.fee, "duration": s.duration_minutes} for s in services
        ]
    }


@router.post("/{doctor_id}/services")
async def add_service(
    doctor_id: UUID,
    service_name: str,
    duration_minutes: int,
    fee: float,
    use_case: Annotated[AddServiceOfferingUseCase, Depends(get_add_service_offering_use_case)],
    description: str | None = None,
):
    result = await use_case.execute(doctor_id, service_name, duration_minutes, fee, description)
    return {"success": True, "service_id": str(result.id)}


@router.put("/{doctor_id}/services/{service_id}")
async def update_service(
    doctor_id: UUID,
    service_id: UUID,
    use_case: Annotated[UpdateServiceOfferingUseCase, Depends(get_update_service_offering_use_case)] = None,
    service_name: str | None = Query(default=None),
    duration_minutes: int | None = Query(default=None),
    fee: float | None = Query(default=None),
    description: str | None = Query(default=None),
):
    update_data = {
        "service_name": service_name,
        "duration_minutes": duration_minutes,
        "fee": fee,
        "description": description,
    }
    update_data = {k: v for k, v in update_data.items() if v is not None}
    await use_case.execute(service_id, **update_data)
    return {"success": True}


@router.delete("/{doctor_id}/services/{service_id}")
async def delete_service(
    doctor_id: UUID,
    service_id: UUID,
    use_case: Annotated[DeactivateServiceOfferingUseCase, Depends(get_deactivate_service_offering_use_case)],
):
    await use_case.execute(service_id)
    return {"success": True}


@router.get("/{doctor_id}/schedule-enhanced")
async def get_enhanced_schedule(
    doctor_id: UUID,
    date: str,
    use_case: Annotated[GetEnhancedScheduleUseCase, Depends(get_enhanced_schedule_use_case)],
):
    from datetime import date as dt_date

    target_date = dt_date.fromisoformat(date)
    return await use_case.execute(doctor_id, target_date)
