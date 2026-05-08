from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from uuid import UUID


class INotificationClient(ABC):
    """Interface for sending notifications via notification_service."""

    @abstractmethod
    async def send_lab_result_ready(
        self,
        patient_id: UUID,
        result_id: UUID,
        test_name: str,
    ) -> None:
        """Notify the patient that their lab result is published."""


class IClinicalServiceClient(ABC):
    """Interface for writing clinical records to clinical_service."""

    @abstractmethod
    async def push_lab_result_to_record(
        self,
        patient_id: UUID,
        doctor_id: UUID,
        result_id: UUID,
        order_id: UUID,
        test_name: str,
        published_text: Optional[str],
        published_findings: Optional[Dict[str, Any]],
    ) -> None:
        """Append a verified lab result as a clinical note in clinical_service."""


class IPatientServiceClient(ABC):
    """Interface for fetching patient profile from patient_service."""

    @abstractmethod
    async def get_patient_name(self, patient_id: UUID) -> Optional[str]:
        """Return the patient's full name, or None if unavailable."""
