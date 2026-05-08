"""
BookingUseCase — handles AI-guided appointment booking after triage recommendation.

Flow:
  1. Frontend receives [R] from SSE → shows specialty recommendation
  2. Patient wants to book → frontend calls POST /triage-sessions/{id}/book
  3. AI asks about preferred date/time → patient responds in next SSE turn
  4. AI calls check_availability_by_department → returns available slots
  5. AI presents slots → patient confirms one
  6. AI calls create_appointment → appointment created with ai_referred=True
  7. Triage session updated with appointment_id
"""
import logging
from typing import Any

from Domain.entities import TriageSession
from Domain.interfaces import ILLMClient
from infrastructure.clients.appointment_service_client import AppointmentServiceClient
from infrastructure.repositories.triage_session_repository import TriageSessionRepository

logger = logging.getLogger(__name__)


class BookingUseCase:
    """
    Manages the post-triage booking sub-dialogue within a TriageSession.

    The AI asks about preferred date/time, checks availability, presents options,
    and creates the appointment when the patient confirms a slot.
    """

    BOOKING_SLOTS_MARKER = "[BOOKING_SLOTS_MARKER]"

    def __init__(
        self,
        llm: ILLMClient,
        appointment_client: AppointmentServiceClient,
        triage_repo: TriageSessionRepository,
    ):
        self._llm = llm
        self._appointment = appointment_client
        self._triage_repo = triage_repo

    async def check_availability_and_suggest(
        self,
        session: TriageSession,
        preferred_date: str,
    ) -> list[dict]:
        """
        Check availability for the suggested department and return available slots.
        Used by the AI to present booking options to the patient.
        """
        department = (
            session.final_department
            or session.suggested_department
        )
        if not department:
            return []

        slots = await self._appointment.check_availability_by_department(
            department=department,
            appointment_date=preferred_date,
        )
        return slots

    async def create_appointment(
        self,
        session: TriageSession,
        doctor_id: str,
        specialty_id: str,
        appointment_date: str,
        start_time: str,
    ) -> dict[str, Any]:
        """
        Create an appointment for the given triage session.
        The appointment is tagged with ai_referred=True so PaymentPaidConsumer
        will enforce manual doctor confirmation.
        """
        result = await self._appointment.create_appointment(
            doctor_id=doctor_id,
            specialty_id=specialty_id,
            appointment_date=appointment_date,
            start_time=start_time,
            patient_id=session.patient_id,
            triage_session_id=session.id,
            urgency_level=session.urgency_level or "Routine",
            referred_by_doctor_id=session.doctor_id or None,
            chief_complaint=None,
        )
        return result

    async def update_session_appointment_id(
        self,
        session_id: str,
        appointment_id: str,
    ) -> None:
        """Update TriageSession with the created appointment_id."""
        session = await self._triage_repo.get_by_id(session_id)
        if session:
            # Add appointment_id tracking via the entity
            session.appointment_id = appointment_id
            await self._triage_repo.save(session)
