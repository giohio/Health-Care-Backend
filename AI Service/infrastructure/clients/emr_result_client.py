import httpx
from infrastructure.config import get_settings
from Domain.interfaces import IEmrResultClient
import logging

logger = logging.getLogger(__name__)


class EmrResultClient(IEmrResultClient):
    def __init__(self):
        s = get_settings()
        self._base    = s.EMR_RESULT_SERVICE_URL
        self._timeout = s.INTERNAL_HTTP_TIMEOUT

    async def get_result(
        self, result_id: str, token: str, x_user_id: str = None, x_user_role: str = None
    ) -> dict:
        """GET /lab-results/{id} — fetch full result record."""
        headers = {"Authorization": f"Bearer {token}"}
        if x_user_id:
            headers["X-User-Id"] = str(x_user_id)
        if x_user_role:
            headers["X-User-Role"] = x_user_role

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}/lab-results/{result_id}",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data") if "data" in data else data

    async def get_recent_results(
        self, patient_id: str, token: str, x_user_id: str, x_user_role: str, limit: int = 5
    ) -> list[dict]:
        """GET /lab-results?patient_id=&status=PUBLISHED — for EMR summary."""
        if not token:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base}/lab-results",
                    params={"patient_id": patient_id,
                            "status": "PUBLISHED",
                            "limit": limit},
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-User-Id": str(x_user_id),
                        "X-User-Role": x_user_role,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning("emr_result_client: get_recent_results fallback for %s: %s", patient_id, e)
            return []

    async def patch_ai_draft(
        self, result_id: str, draft: dict, x_user_id: str = None, x_user_role: str = "service"
    ) -> None:
        """PATCH /lab-results/{id}/ai-draft — called by Celery after pipeline completes."""
        headers = {"X-User-Role": x_user_role}
        if x_user_id:
            headers["X-User-Id"] = str(x_user_id)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.patch(
                f"{self._base}/lab-results/{result_id}/ai-draft",
                json=draft,
                headers=headers,
            )
            resp.raise_for_status()

    async def get_published_results_for_appointment(
        self, appointment_id: str, x_user_role: str = "service"
    ) -> list[dict]:
        """Fetch all PUBLISHED lab results for an appointment via readiness endpoint."""
        # Step 1: get order_ids from readiness
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            readiness_resp = await client.get(
                f"{self._base}/lab-orders/{appointment_id}/readiness",
                headers={"X-User-Role": x_user_role, "X-User-Id": "00000000-0000-0000-0000-000000000001"},
            )
            readiness_resp.raise_for_status()
            readiness = readiness_resp.json()

        result_ids = [
            r["result_id"]
            for r in readiness.get("results", [])
            if r.get("result_id") and r.get("status") == "PUBLISHED"
        ]
        if not result_ids:
            return []

        # Step 2: fetch each result by ID
        results = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for rid in result_ids:
                try:
                    resp = await client.get(
                        f"{self._base}/lab-results/{rid}",
                        headers={"X-User-Role": x_user_role, "X-User-Id": "00000000-0000-0000-0000-000000000001"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    results.append(data if isinstance(data, dict) else data.get("data", {}))
                except Exception as e:
                    logger.warning("Could not fetch result %s for holistic analysis: %s", rid, e)
        return results

    async def patch_holistic_summary(
        self, appointment_id: str, payload: dict, x_user_role: str = "service"
    ) -> None:
        """PATCH /appointments/{id}/lab-summary — push holistic text back to EMR Result Service."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.patch(
                f"{self._base}/appointments/{appointment_id}/lab-summary",
                json=payload,
                headers={"X-User-Role": x_user_role},
            )
            resp.raise_for_status()
