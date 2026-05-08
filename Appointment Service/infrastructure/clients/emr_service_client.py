"""HTTP client for the EMR Result Service.

Used by the Appointment Service to fetch lab readiness status for
appointments in the doctor queue.
"""
import logging
from typing import Any, Dict, Optional
from uuid import UUID

import httpx
from healthai_cache import CacheClient
from healthai_common import CircuitBreaker
from infrastructure.config import settings

logger = logging.getLogger(__name__)


class EmrServiceClient:
    def __init__(
        self,
        cache: CacheClient,
        base_url: str = settings.EMR_SERVICE_URL,
    ):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=3.0)
        self._cb = CircuitBreaker(
            name="emr_service",
            cache=cache,
            failure_threshold=5,
            recovery_timeout=30,
        )

    async def get_lab_readiness(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        """Fetch lab readiness for an appointment.

        Returns the readiness dict or ``None`` on failure.
        """
        async def _fetch():
            response = await self._client.get(
                f"/lab-orders/{appointment_id}/readiness",
                headers={"X-User-Role": "admin", "X-User-Id": "00000000-0000-0000-0000-000000000000"},
            )
            response.raise_for_status()
            return response.json()

        async def _fallback(*_args, **_kwargs):
            import asyncio
            await asyncio.sleep(0)
            return None

        return await self._cb.call(_fetch, fallback=_fallback)
