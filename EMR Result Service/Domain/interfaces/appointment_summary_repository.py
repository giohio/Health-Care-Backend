from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from Domain.entities.appointment_lab_summary import AppointmentLabSummary


class IAppointmentSummaryRepository(ABC):
    @abstractmethod
    async def save(self, summary: AppointmentLabSummary) -> AppointmentLabSummary:
        """Insert or update an AppointmentLabSummary."""

    @abstractmethod
    async def get_by_appointment_id(self, appointment_id: UUID) -> Optional[AppointmentLabSummary]:
        """Return the summary for an appointment, or None."""
