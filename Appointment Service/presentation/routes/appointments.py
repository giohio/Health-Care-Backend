from datetime import date
from typing import Annotated, List
from uuid import UUID

from Application.dtos import (
    AppointmentResponse,
    AvailableSlotsResponse,
    CancelAppointmentRequest,
    CreateAppointmentRequest,
    DeclineAppointmentRequest,
    DoctorQueueItemResponse,
    RescheduleAppointmentRequest,
)
from Application.use_cases.book_appointment import BookAppointmentUseCase
from Application.use_cases.cancel_appointment import CancelAppointmentUseCase
from Application.use_cases.complete_appointment import CompleteAppointmentUseCase
from Application.use_cases.confirm_appointment import ConfirmAppointmentUseCase
from Application.use_cases.decline_appointment import DeclineAppointmentUseCase
from Application.use_cases.get_available_slots import GetAvailableSlotsUseCase
from Application.use_cases.get_doctor_queue import GetDoctorQueueUseCase
from Application.use_cases.list_patient_appointments import ListPatientAppointmentsUseCase
from Application.use_cases.mark_no_show import MarkNoShowUseCase
from Application.use_cases.reschedule_appointment import RescheduleAppointmentUseCase
from Domain.exceptions.domain_exceptions import (
    AppointmentNotFoundException,
    InvalidStatusTransitionError,
    SlotNotAvailableError,
    UnauthorizedActionError,
)
from fastapi import APIRouter, Depends, Header, HTTPException
from healthai_common import SagaFailedError
from presentation.dependencies import (
    get_available_slots_use_case,
    get_book_appointment_use_case,
    get_cancel_appointment_use_case,
    get_complete_appointment_use_case,
    get_confirm_appointment_use_case,
    get_decline_appointment_use_case,
    get_doctor_queue_use_case,
    get_list_appointments_use_case,
    get_mark_no_show_use_case,
    get_reschedule_appointment_use_case,
)

router = APIRouter(tags=["Appointments"])


@router.post("/", response_model=AppointmentResponse, responses={400: {"description": "No doctor available"}})
async def book_appointment(
    request: CreateAppointmentRequest,
    use_case: Annotated[BookAppointmentUseCase, Depends(get_book_appointment_use_case)],
):
    try:
        return await use_case.execute(request)
    except SlotNotAvailableError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except SagaFailedError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/patient/{patient_id}", response_model=List[AppointmentResponse])
async def list_patient_appointments(
    patient_id: UUID, use_case: Annotated[ListPatientAppointmentsUseCase, Depends(get_list_appointments_use_case)]
):
    return await use_case.execute(patient_id)


@router.put(
    "/{appointment_id}/cancel",
    response_model=AppointmentResponse,
    responses={404: {"description": "Appointment not found"}},
)
async def cancel_appointment(
    appointment_id: UUID,
    request: CancelAppointmentRequest,
    use_case: Annotated[CancelAppointmentUseCase, Depends(get_cancel_appointment_use_case)],
    x_user_id: Annotated[UUID, Header(alias="X-User-Id")],
    x_user_role: Annotated[str, Header(alias="X-User-Role")],
):
    try:
        return await use_case.execute(
            appointment_id,
            x_user_id,
            x_user_role,
            request.reason,
        )
    except AppointmentNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedActionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{appointment_id}/confirm", response_model=AppointmentResponse)
async def confirm_appointment(
    appointment_id: UUID,
    use_case: Annotated[ConfirmAppointmentUseCase, Depends(get_confirm_appointment_use_case)],
    x_user_id: Annotated[UUID, Header(alias="X-User-Id")],
):
    try:
        return await use_case.execute(appointment_id, x_user_id)
    except AppointmentNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedActionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{appointment_id}/decline", response_model=AppointmentResponse)
async def decline_appointment(
    appointment_id: UUID,
    request: DeclineAppointmentRequest,
    use_case: Annotated[DeclineAppointmentUseCase, Depends(get_decline_appointment_use_case)],
    x_user_id: Annotated[UUID, Header(alias="X-User-Id")],
):
    try:
        return await use_case.execute(appointment_id, x_user_id, request.reason)
    except AppointmentNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedActionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_appointment(
    appointment_id: UUID,
    request: RescheduleAppointmentRequest,
    use_case: Annotated[RescheduleAppointmentUseCase, Depends(get_reschedule_appointment_use_case)],
    x_user_id: Annotated[UUID, Header(alias="X-User-Id")],
):
    try:
        return await use_case.execute(
            appointment_id,
            x_user_id,
            request.new_date,
            request.new_time,
        )
    except AppointmentNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedActionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SlotNotAvailableError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/{appointment_id}/complete", response_model=AppointmentResponse)
async def complete_appointment(
    appointment_id: UUID,
    use_case: Annotated[CompleteAppointmentUseCase, Depends(get_complete_appointment_use_case)],
    x_user_id: Annotated[UUID, Header(alias="X-User-Id")],
):
    try:
        return await use_case.execute(appointment_id, x_user_id)
    except AppointmentNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedActionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{appointment_id}/no-show", response_model=AppointmentResponse)
async def mark_no_show(
    appointment_id: UUID,
    use_case: Annotated[MarkNoShowUseCase, Depends(get_mark_no_show_use_case)],
    x_user_id: Annotated[UUID, Header(alias="X-User-Id")],
):
    try:
        return await use_case.execute(appointment_id, x_user_id)
    except AppointmentNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedActionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/doctor/{doctor_id}/slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    doctor_id: UUID,
    appointment_date: date,
    specialty_id: UUID,
    use_case: Annotated[GetAvailableSlotsUseCase, Depends(get_available_slots_use_case)],
    appointment_type: str = "general",
):
    return await use_case.execute(
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        specialty_id=specialty_id,
        appointment_type=appointment_type,
    )


@router.get("/doctor/{doctor_id}/queue", response_model=List[DoctorQueueItemResponse])
async def get_doctor_queue(
    doctor_id: UUID,
    appointment_date: date,
    use_case: Annotated[GetDoctorQueueUseCase, Depends(get_doctor_queue_use_case)],
):
    return await use_case.execute(doctor_id, appointment_date)
