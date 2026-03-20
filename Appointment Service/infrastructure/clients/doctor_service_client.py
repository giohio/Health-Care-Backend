import httpx
from typing import List, Dict, Any
from uuid_extension import UUID7
from datetime import time
import logging
from Domain.interfaces.doctor_service_client import IDoctorServiceClient
from infrastructure.config import settings

logger = logging.getLogger(__name__)

class DoctorServiceClient(IDoctorServiceClient):
    def __init__(self, base_url: str = settings.DOCTOR_SERVICE_URL):
        self.base_url = base_url

    async def get_available_doctors(self, specialty_id: UUID7, day_of_week: int, time_slot: time) -> List[Dict[str, Any]]:
        """
        Calls Doctor Service to find doctors.
        We expect an endpoint like /doctors/available?specialty_id=...&day=...&time=...
        """
        url = f"{self.base_url}/search/available"
        params = {
            "specialty_id": str(specialty_id),
            "day": day_of_week,
            "time": time_slot.strftime("%H:%M")
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=5.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to call Doctor Service: {e}")
            return []
