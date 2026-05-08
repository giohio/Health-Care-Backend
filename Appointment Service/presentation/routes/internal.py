from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from infrastructure.repositories.appointment_repository import AppointmentRepository
from presentation.dependencies import (
    get_appointment_repo,
    get_event_publisher,
    get_cache_client,
)
from Domain.interfaces.event_publisher import IEventPublisher
from infrastructure.database.session import AsyncSessionLocal
from healthai_cache import CacheClient
from Application.use_cases.mark_overdue_appointment import MarkOverdueAppointmentUseCase

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


@router.post("/internal/overdue-check")
async def check_overdue_appointments(
    event_publisher: Annotated[IEventPublisher, Depends(get_event_publisher)],
    cache: Annotated[CacheClient | None, Depends(get_cache_client)] = None,
):
    """
    Scan all CONFIRMED appointments whose scheduled end_time has passed and
    mark them as OVERDUE. Called periodically by Notification Service scheduler.
    """
    async with AsyncSessionLocal() as session:
        repo = AppointmentRepository(session)
        now = datetime.now()
        overdue_appts = await repo.get_confirmed_past_end_time(now)

    processed = 0
    errors = []

    for appt in overdue_appts:
        try:
            async with AsyncSessionLocal() as session:
                repo_for_use_case = AppointmentRepository(session)
                use_case = MarkOverdueAppointmentUseCase(
                    session=session,
                    appointment_repo=repo_for_use_case,
                    event_publisher=event_publisher,
                    cache=cache,
                )
                await use_case.execute(appt.id, reason="system_overdue")
            processed += 1
        except Exception as exc:
            errors.append({"appointment_id": str(appt.id), "error": str(exc)})

    return {"processed": processed, "errors": errors}
