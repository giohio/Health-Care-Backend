"""
Booking tool implementations for Groq tool-calling.
Each tool_call invokes one of these functions and the result is fed back to the AI.
"""
from __future__ import annotations

import logging
from typing import Any

from infrastructure.clients.appointment_service_client import AppointmentServiceClient

logger = logging.getLogger(__name__)


async def fn_check_availability(
    department: str,
    date: str,
) -> dict[str, Any]:
    """
    Tool handler for the `check_availability` tool.
    Returns a serialized dict of slots (or error) that gets injected into the LLM conversation.
    """
    try:
        client = AppointmentServiceClient()
        specialty_name = client.resolve_department_to_specialty(department)
        if not specialty_name:
            return {
                "status": "unsupported_department",
                "department": department,
                "date": date,
                "supported_departments": list(client._SUPPORTED_DEPARTMENTS),
                "message": (
                    f"Department '{department}' is not available for booking in this system."
                ),
            }

        doctors = await client.get_doctors_by_specialty(specialty_name)
        if not doctors:
            return {
                "status": "no_doctors",
                "department": department,
                "date": date,
                "message": (
                    f"No active doctors found for {specialty_name} right now."
                ),
            }

        slots = await client.check_availability_by_department(
            department=department,
            appointment_date=date,
        )
        if not slots:
            return {
                "status": "no_slots_for_date",
                "department": department,
                "date": date,
                "message": f"No available slots for {department} on {date}.",
            }

        return {
            "status": "ok",
            "department": department,
            "date": date,
            "slots": [
                {
                    "doctor_id": s["doctor_id"],
                    "doctor_name": s["doctor_name"],
                    "specialty_id": s["specialty_id"],
                    "start_time": s["start_time"],
                    "end_time": s["end_time"],
                }
                for s in slots
            ],
        }
    except Exception as e:
        logger.error("fn_check_availability error: %s", e)
        return {"status": "error", "message": str(e)}


async def fn_create_appointment(
    doctor_id: str,
    specialty_id: str,
    date: str,
    time: str,
    patient_id: str,
    session_id: str,
    department: str,
    urgency_level: str = "Routine",
    doctor_name: str = "",
) -> dict[str, Any]:
    """
    Create a real appointment record in Appointment Service so it is visible
    in the patient's My Appointments list, while keeping AI chat wording as
    pending review.
    """
    try:
        client = AppointmentServiceClient()
        created = await client.create_appointment(
            doctor_id=doctor_id,
            specialty_id=specialty_id,
            appointment_date=date,
            start_time=time,
            patient_id=patient_id,
            triage_session_id=(session_id or None),
            urgency_level=urgency_level,
            referred_by_doctor_id=None,
            chief_complaint=None,
        )
        if created.get("error"):
            return {"status": "error", "message": created.get("error")}

        appointment_id = created.get("id")
        if not appointment_id:
            return {
                "status": "error",
                "message": "Appointment was not created successfully.",
            }

        return {
            "status": "pending_review",
            "appointment_id": appointment_id,
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "date": date,
            "time": time,
            "department": department,
            "message": (
                f"Your booking request has been submitted! "
                f"Dr. {doctor_name} on {date} at {time} is now pending doctor review. "
                f"You will be notified once the doctor confirms your appointment."
            ),
        }
    except Exception as e:
        logger.error("fn_create_appointment error: %s", e)
        return {"status": "error", "message": str(e)}