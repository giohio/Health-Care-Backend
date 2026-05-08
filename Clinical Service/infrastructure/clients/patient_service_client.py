import asyncio
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from Domain.interfaces.patient_service_client import IPatientServiceClient
from healthai_common import CircuitBreaker
from healthai_cache import CacheClient
from infrastructure.config import settings

logger = logging.getLogger(__name__)


class PatientServiceClient(IPatientServiceClient):
    """HTTP client for reading patient data from patient_service.

    Uses a Circuit Breaker backed by Redis so repeated failures do not
    cascade into clinical_service.
    """

    def __init__(
        self,
        cache: CacheClient,
        base_url: str = settings.PATIENT_SERVICE_URL,
    ):
        self.base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=3.0)
        self._cb = CircuitBreaker(
            name="patient_service",
            cache=cache,
            failure_threshold=5,
            recovery_timeout=30,
        )

    # ------------------------------------------------------------------
    # IPatientServiceClient implementation
    # ------------------------------------------------------------------

    async def get_allergies(self, patient_id: UUID) -> List[str]:
        async def _fetch() -> List[str]:
            response = await self._client.get(f"/patients/{patient_id}/health-background")
            response.raise_for_status()
            data = response.json()
            # patient_service returns { allergies: [...] } inside health background
            return data.get("allergies") or []

        async def _fallback(*_args, **_kwargs) -> List[str]:
            await asyncio.sleep(0)
            logger.warning(
                "PatientServiceClient.get_allergies fallback for patient_id=%s", patient_id
            )
            return []

        return await self._cb.call(_fetch, fallback=_fallback)

    async def get_latest_vitals(self, patient_id: UUID) -> Optional[Dict[str, Any]]:
        async def _fetch() -> Optional[Dict[str, Any]]:
            response = await self._client.get(f"/patients/{patient_id}/vitals/latest")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

        async def _fallback(*_args, **_kwargs) -> Optional[Dict[str, Any]]:
            await asyncio.sleep(0)
            logger.warning(
                "PatientServiceClient.get_latest_vitals fallback for patient_id=%s", patient_id
            )
            return None

        return await self._cb.call(_fetch, fallback=_fallback)
