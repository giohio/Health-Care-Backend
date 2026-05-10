from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from uuid import UUID


class IPatientServiceClient(ABC):
    """Interface for reading patient-owned data (allergies, vitals) from patient_service."""

    @abstractmethod
    async def get_allergies(self, patient_id: UUID) -> List[str]:
        """Return the patient's allergy list. Returns an empty list on failure."""

    @abstractmethod
    async def get_latest_vitals(self, patient_id: UUID) -> Optional[Dict[str, Any]]:
        """Return the most-recent vitals snapshot for the patient, or None.

        Expected shape (same as patient_service response):
        {
            "height_cm": float | None,
            "weight_kg": float | None,
            "blood_pressure": str | None,
            "heart_rate": int | None,
            "temperature_celsius": float | None,
            "oxygen_saturation": int | None,
            "recorded_at": str | None,
        }
        """
