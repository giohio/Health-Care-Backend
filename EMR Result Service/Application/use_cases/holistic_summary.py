"""Use cases for the AppointmentLabSummary (holistic cross-result analysis)."""
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from Application.dtos import AppointmentLabSummaryResponse, UpdateHolisticSummaryRequest, ReviewHolisticSummaryRequest
from Application.exceptions import LabResultNotFoundError
from Domain.entities.appointment_lab_summary import AppointmentSummaryStatus
from Domain.interfaces.appointment_summary_repository import IAppointmentSummaryRepository
import logging

logger = logging.getLogger(__name__)


class GetHolisticSummaryUseCase:
    def __init__(self, summary_repo: IAppointmentSummaryRepository):
        self._repo = summary_repo

    async def execute(self, appointment_id: UUID) -> Optional[AppointmentLabSummaryResponse]:
        summary = await self._repo.get_by_appointment_id(appointment_id)
        if summary is None:
            return None
        return AppointmentLabSummaryResponse(
            id=summary.id,
            appointment_id=summary.appointment_id,
            patient_id=summary.patient_id,
            status=summary.status,
            ai_holistic_text=summary.ai_holistic_text,
            total_results=summary.total_results,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            doctor_conclusion=summary.doctor_conclusion,
            reviewed_by=summary.reviewed_by,
            reviewed_at=summary.reviewed_at,
        )


class UpdateHolisticSummaryUseCase:
    """Called by AI Service (role=service) to patch the holistic text once done."""

    def __init__(self, summary_repo: IAppointmentSummaryRepository):
        self._repo = summary_repo

    async def execute(
        self, appointment_id: UUID, request: UpdateHolisticSummaryRequest
    ) -> AppointmentLabSummaryResponse:
        summary = await self._repo.get_by_appointment_id(appointment_id)
        if summary is None:
            raise LabResultNotFoundError()

        summary.ai_holistic_text = request.ai_holistic_text
        summary.status = request.status

        saved = await self._repo.save(summary)
        logger.info(
            "Holistic summary updated for appointment %s — status=%s", appointment_id, saved.status
        )
        return AppointmentLabSummaryResponse(
            id=summary.id,
            appointment_id=summary.appointment_id,
            patient_id=summary.patient_id,
            status=summary.status,
            ai_holistic_text=summary.ai_holistic_text,
            total_results=summary.total_results,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            doctor_conclusion=summary.doctor_conclusion,
            reviewed_by=summary.reviewed_by,
            reviewed_at=summary.reviewed_at,
        )


class ReviewHolisticSummaryUseCase:
    """Doctor adds their clinical conclusion to the AI holistic summary."""

    def __init__(self, summary_repo: IAppointmentSummaryRepository):
        self._repo = summary_repo

    async def execute(
        self, appointment_id: UUID, doctor_id: UUID, request: ReviewHolisticSummaryRequest
    ) -> AppointmentLabSummaryResponse:
        summary = await self._repo.get_by_appointment_id(appointment_id)
        if summary is None:
            raise LabResultNotFoundError()

        summary.doctor_conclusion = request.doctor_conclusion.strip()
        summary.reviewed_by = doctor_id
        summary.reviewed_at = datetime.now(timezone.utc)

        saved = await self._repo.save(summary)
        logger.info(
            "Holistic summary reviewed by doctor %s for appointment %s",
            doctor_id, appointment_id,
        )
        return AppointmentLabSummaryResponse(
            id=saved.id,
            appointment_id=saved.appointment_id,
            patient_id=saved.patient_id,
            status=saved.status,
            ai_holistic_text=saved.ai_holistic_text,
            total_results=saved.total_results,
            created_at=saved.created_at,
            updated_at=saved.updated_at,
            doctor_conclusion=saved.doctor_conclusion,
            reviewed_by=saved.reviewed_by,
            reviewed_at=saved.reviewed_at,
        )
