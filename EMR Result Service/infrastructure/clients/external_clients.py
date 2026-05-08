import asyncio
import logging
from typing import Any, Dict, Optional
from uuid import UUID

import httpx
from Domain.interfaces.external_clients import IClinicalServiceClient, INotificationClient, IPatientServiceClient
from healthai_cache import CacheClient
from healthai_common import CircuitBreaker
from infrastructure.config import settings

logger = logging.getLogger(__name__)


class NotificationClient(INotificationClient):
    """HTTP client for notification_service — sends push events to patients."""

    def __init__(
        self,
        cache: CacheClient,
        base_url: str = settings.NOTIFICATION_SERVICE_URL,
    ):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=5.0)
        self._cb = CircuitBreaker(
            name="notification_service_from_emr",
            cache=cache,
            failure_threshold=5,
            recovery_timeout=30,
        )

    async def send_lab_result_ready(
        self,
        patient_id: UUID,
        result_id: UUID,
        test_name: str,
    ) -> None:
        async def _push() -> None:
            response = await self._client.post(
                "/notifications/internal",
                json={
                    "user_id": str(patient_id),
                    "type": "LAB_RESULT_READY",
                    "title": "Lab Result Available",
                    "body": f"Your {test_name} result is now available.",
                    "metadata": {"result_id": str(result_id)},
                },
            )
            response.raise_for_status()

        async def _fallback(*_args, **_kwargs) -> None:
            await asyncio.sleep(0)
            logger.warning(
                "NotificationClient fallback — notification not delivered for result_id=%s",
                result_id,
            )

        await self._cb.call(_push, fallback=_fallback)


class PatientServiceClient(IPatientServiceClient):
    """HTTP client for patient_service — fetches patient name for PDF reports."""

    def __init__(
        self,
        cache: CacheClient,
        base_url: str = settings.PATIENT_SERVICE_URL,
    ):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=5.0)
        self._cb = CircuitBreaker(
            name="patient_service_from_emr",
            cache=cache,
            failure_threshold=5,
            recovery_timeout=30,
        )

    async def get_patient_name(self, patient_id: UUID) -> Optional[str]:
        async def _fetch() -> Optional[str]:
            response = await self._client.get(
                f"/internal/patients/{patient_id}/full-context",
                headers={"X-User-Role": "service"},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            # Profile schema uses full_name (not first_name/last_name)
            profile = data.get("profile", {})
            full_name = profile.get("full_name") or ""
            return full_name if full_name else None

        async def _fallback(*_args, **_kwargs) -> Optional[str]:
            await asyncio.sleep(0)
            logger.warning("PatientServiceClient fallback — name unavailable for patient_id=%s", patient_id)
            return None

        return await self._cb.call(_fetch, fallback=_fallback)


class ClinicalServiceClient(IClinicalServiceClient):
    """HTTP client for writing verified lab results into clinical_service."""

    def __init__(
        self,
        cache: CacheClient,
        base_url: str = settings.CLINICAL_SERVICE_URL,
    ):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=5.0)
        self._cb = CircuitBreaker(
            name="clinical_service_from_emr",
            cache=cache,
            failure_threshold=5,
            recovery_timeout=30,
        )

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
        content = published_text or f"Lab result for order {order_id} verified."
        if published_findings:
            content += f"\n\nFindings: {published_findings}"

        async def _push() -> None:
            response = await self._client.post(
                f"/clinical/patients/{patient_id}/notes",
                headers={
                    "X-User-Id": str(doctor_id),
                    "X-User-Role": "doctor",
                },
                json={
                    "patient_id": str(patient_id),
                    "doctor_id": str(doctor_id),
                    "content": content,
                    "note_type": "summary",
                    "is_ai_generated": False,
                },
            )
            response.raise_for_status()

        async def _fallback(*_args, **_kwargs) -> None:
            await asyncio.sleep(0)
            logger.error(
                "ClinicalServiceClient fallback — lab result %s NOT written to clinical record",
                result_id,
            )

        await self._cb.call(_push, fallback=_fallback)
