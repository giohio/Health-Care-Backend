from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from infrastructure.repositories.appointment_repository import AppointmentRepository
from presentation.dependencies import get_appointment_repo

router = APIRouter(tags=["Internal"])


@router.get("/internal/upcoming")
async def get_upcoming_appointments(
    start_time: str, end_time: str, repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]
):
    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)
    appointments = await repo.get_upcoming_for_reminders(start_dt, end_dt)
    return [
        {
            "id": str(a.id),
            "patient_id": str(a.patient_id),
            "appointment_date": str(a.appointment_date),
            "start_time": str(a.start_time),
            "reminder_24h_sent": a.reminder_24h_sent,
            "reminder_1h_sent": a.reminder_1h_sent,
        }
        for a in appointments
    ]


@router.put("/internal/{appointment_id}/reminder-sent")
async def mark_reminder_sent(
    appointment_id: UUID, reminder_type: str, repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]
):
    await repo.mark_reminder_sent(appointment_id, reminder_type)
    return {"success": True}


@router.get("/internal/has-completed")
async def has_completed_appointment(
    patient_id: UUID, doctor_id: UUID, repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]
):
    has_completed = await repo.has_completed_appointment(patient_id, doctor_id)
    return {"has_completed": has_completed}


@router.get("/internal/appointments/{appointment_id}")
async def get_appointment(appointment_id: UUID, repo: Annotated[AppointmentRepository, Depends(get_appointment_repo)]):
    appointment = await repo.get_by_id(appointment_id)
    if not appointment:
        return None
    return {
        "id": str(appointment.id),
        "patient_id": str(appointment.patient_id),
        "doctor_id": str(appointment.doctor_id),
        "status": appointment.status,
    }
