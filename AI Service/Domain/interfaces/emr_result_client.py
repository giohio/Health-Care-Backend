from abc import ABC, abstractmethod


class IEmrResultClient(ABC):
    """Abstract interface for communicating with the EMR Result Service."""

    @abstractmethod
    async def get_result(self, result_id: str, token: str) -> dict:
        """Fetch a single lab result record by ID."""
        ...

    @abstractmethod
    async def get_recent_results(
        self, patient_id: str, token: str, x_user_id: str, x_user_role: str, limit: int = 5
    ) -> list[dict]:
        """Fetch the most recent published results for a patient."""
        ...

    @abstractmethod
    async def patch_ai_draft(self, result_id: str, draft: dict, x_user_role: str) -> None:
        """Push AI pipeline output to the EMR Result Service."""
        ...

    @abstractmethod
    async def get_published_results_for_appointment(
        self, appointment_id: str, x_user_role: str = "service"
    ) -> list[dict]:
        """Fetch all PUBLISHED lab results for an appointment (for holistic analysis)."""
        ...

    @abstractmethod
    async def patch_holistic_summary(
        self, appointment_id: str, payload: dict, x_user_role: str = "service"
    ) -> None:
        """PATCH the AppointmentLabSummary record with holistic text."""
        ...
