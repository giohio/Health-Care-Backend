import httpx
from infrastructure.config import get_settings
import logging

logger = logging.getLogger(__name__)


class PatientServiceClient:
    """Lightweight client to fetch patient profile from patient_service."""

    def __init__(self):
        s = get_settings()
        self._base_url = s.PATIENT_SERVICE_URL
        self._timeout = s.INTERNAL_HTTP_TIMEOUT

    async def get_patient_name(self, patient_id: str) -> str | None:
        """
        Fetch the patient's full_name from patient_service.
        Returns None on failure (caller should handle gracefully).
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/internal/patients/{patient_id}",
                )
                resp.raise_for_status()
                data = resp.json()
                # Support both wrapped {data: {...}} and flat responses
                if isinstance(data, dict) and "data" in data:
                    data = data["data"]
                return data.get("full_name") or data.get("profile", {}).get("full_name")
        except Exception as e:
            logger.warning("patient_service_client: failed to fetch name for %s: %s", patient_id, e)
            return None
