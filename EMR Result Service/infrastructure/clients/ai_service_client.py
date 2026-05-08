import logging
from uuid import UUID

import httpx

from infrastructure.config import settings

logger = logging.getLogger(__name__)


class AiServiceClient:
    """Fire-and-forget HTTP client that enqueues a Celery lab analysis job.

    Errors are intentionally swallowed — a failed trigger is logged and the
    result stays in PENDING status for manual follow-up.  This must NEVER block
    the main request/response cycle.
    """

    _TIMEOUT = 5.0  # seconds — short enough not to block the upload response

    async def trigger_lab_analysis(
        self,
        result_id: UUID,
        patient_id: UUID,
        file_url: str | None,
        file_type: str,
        department: str,
        test_name: str,
        auth_token: str,
        x_user_id: str = "system",
        x_user_role: str = "service",
        tabular_data: dict | None = None,
    ) -> None:
        """
        Notify the AI Service to begin processing a new lab result.
        This is a 'fire and forget' background call from the perspective of the route handler.
        """
        # Determine if we should treat this as a structured table or an image/file
        input_type = "tabular" if file_type in ("manual", "csv", "tabular") else "image"

        payload = {
            "result_id": str(result_id),
            "patient_id": str(patient_id),
            "file_url": file_url,
            "input_type": input_type,
            "department": department,
            "test_name": test_name,
            "auth_token": auth_token,
            "tabular_data": tabular_data,
        }

        # Defensively prepare headers (FastAPI/Httpx can be picky about None vs strings)
        headers = {}
        if x_user_id:
            headers["X-User-Id"] = str(x_user_id)
        if x_user_role:
            headers["X-User-Role"] = str(x_user_role)

        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                resp = await client.post(
                    f"{settings.AI_SERVICE_URL}/analyze-lab",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                logger.info(
                    "Successfully triggered AI analysis (%s) for result %s",
                    input_type,
                    result_id,
                )
        except Exception as e:
            logger.error(
                "Failed to trigger AI analysis for result %s: %s",
                result_id,
                e,
                exc_info=True,
            )

    async def trigger_holistic_analysis(
        self,
        appointment_id: UUID,
        patient_id: UUID,
        summary_id: UUID,
        x_user_role: str = "service",
    ) -> None:
        """Fire-and-forget: ask AI Service to run the cross-result holistic analysis."""
        payload = {
            "appointment_id": str(appointment_id),
            "patient_id": str(patient_id),
            "summary_id": str(summary_id),
        }
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                resp = await client.post(
                    f"{settings.AI_SERVICE_URL}/analyze-all-labs",
                    json=payload,
                    headers={"X-User-Role": x_user_role},
                )
                resp.raise_for_status()
                logger.info("Holistic analysis enqueued for appointment_id=%s", appointment_id)
        except Exception:
            logger.warning(
                "Could not enqueue holistic analysis for appointment_id=%s (non-fatal)",
                appointment_id,
                exc_info=True,
            )
