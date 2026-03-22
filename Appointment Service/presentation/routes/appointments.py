from fastapi import APIRouter, Depends, HTTPException
from typing import List
from uuid import UUID
from Application.dtos import CreateAppointmentRequest, AppointmentResponse
from Application.use_cases.book_appointment import BookAppointmentUseCase
from Application.use_cases.list_patient_appointments import ListPatientAppointmentsUseCase
from Application.use_cases.cancel_appointment import CancelAppointmentUseCase
from Application.exceptions import (
    AppointmentError,
    SlotNotAvailableError,
    DoctorNotAvailableError,
)
from presentation.dependencies import (
    get_book_appointment_use_case, 
    get_list_appointments_use_case, 
    get_cancel_appointment_use_case
)
from Domain.exceptions.domain_exceptions import AppointmentNotFoundException
from typing import Annotated

router = APIRouter(tags=["Appointments"])

@router.post("/", response_model=AppointmentResponse, responses={400: {"description": "No doctor available"}})
async def book_appointment(
    request: CreateAppointmentRequest,
    use_case: Annotated[BookAppointmentUseCase, Depends(get_book_appointment_use_case)]
):
    try:
        return await use_case.execute(request)
    except SlotNotAvailableError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except DoctorNotAvailableError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AppointmentError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/patient/{patient_id}", response_model=List[AppointmentResponse])
async def list_patient_appointments(
    patient_id: UUID,
    use_case: Annotated[ListPatientAppointmentsUseCase, Depends(get_list_appointments_use_case)]
):
    return await use_case.execute(patient_id)

@router.put("/{appointment_id}/cancel", response_model=AppointmentResponse, responses={404: {"description": "Appointment not found"}})
async def cancel_appointment(
    appointment_id: UUID,
    use_case: Annotated[CancelAppointmentUseCase, Depends(get_cancel_appointment_use_case)]
):
    try:
        return await use_case.execute(appointment_id)
    except AppointmentNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
