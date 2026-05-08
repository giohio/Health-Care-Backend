import logging

import httpx

logger = logging.getLogger(__name__)


class AuthServiceClient:
    def __init__(self, base_url: str = "http://auth_service:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def get_user_email(self, user_id: str) -> str | None:
        try:
            response = await self.client.get(f"/internal/users/{user_id}")
            if response.status_code == 200:
                return response.json().get("email")
            return None
        except Exception:
            logger.warning("Failed to fetch email for user %s from auth service", user_id)
            return None
