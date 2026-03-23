import asyncio
import logging
from datetime import time
from typing import Any, Dict, List

import httpx
from Domain.interfaces.doctor_service_client import IDoctorServiceClient
from healthai_cache import CacheClient
from healthai_common import CircuitBreaker
from infrastructure.config import settings
from uuid_extension import UUID7

logger = logging.getLogger(__name__)


class DoctorServiceClient(IDoctorServiceClient):
    def __init__(
        self,
        cache: CacheClient,
        base_url: str = settings.DOCTOR_SERVICE_URL,
    ):
        self.base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=3.0)
        self._cb = CircuitBreaker(
            name="doctor_service",
            cache=cache,
            failure_threshold=5,
            recovery_timeout=30,
        )

    async def get_available_doctors(
        self, specialty_id: UUID7, day_of_week: int, time_slot: time
    ) -> List[Dict[str, Any]]:
        """
        Calls Doctor Service to find doctors.
        We expect an endpoint like /doctors/available?specialty_id=...&day=...&time=...
        """

        async def _fetch():
            response = await self._client.get(
                "/search/available",
                params={
                    "specialty_id": str(specialty_id),
                    "day": day_of_week,
                    "time": time_slot.strftime("%H:%M"),
                },
            )
            response.raise_for_status()
            return response.json()

        async def _fallback(*_args, **_kwargs):
            await asyncio.sleep(0)
            return []

        return await self._cb.call(_fetch, fallback=_fallback)

    async def get_schedule(self, doctor_id: str) -> dict | None:
        async def _fetch():
            response = await self._client.get(f"/{doctor_id}/schedule")
            response.raise_for_status()
            return response.json()

        async def _fallback(*_args, **_kwargs):
            await asyncio.sleep(0)
            return None

        return await self._cb.call(_fetch, fallback=_fallback)

    async def get_type_config(self, specialty_id: str, appointment_type: str) -> dict | None:
        # Placeholder path; can be wired to dedicated endpoint when available.
        async def _fetch():
            response = await self._client.get(
                "/appointments/type-configs",
                params={"specialty_id": specialty_id, "type": appointment_type},
            )
            response.raise_for_status()
            return response.json()

        async def _fallback(*_args, **_kwargs):
            await asyncio.sleep(0)
            return None

        return await self._cb.call(_fetch, fallback=_fallback)

    async def get_patient_full_context(self, patient_id: str) -> dict | None:
        async def _fetch():
            response = await self._client.get(f"/patients/internal/patients/{patient_id}/full-context")
            response.raise_for_status()
            return response.json()

        async def _fallback(*_args, **_kwargs):
            await asyncio.sleep(0)
            return None

        return await self._cb.call(_fetch, fallback=_fallback)
