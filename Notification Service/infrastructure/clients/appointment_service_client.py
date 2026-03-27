from datetime import datetime

import httpx


class AppointmentServiceClient:
    def __init__(self, base_url: str = "http://appointment-service:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def get_upcoming_appointments(self, start_time: datetime, end_time: datetime):
        try:
            response = await self.client.get(
                "/internal/upcoming", params={"start_time": start_time.isoformat(), "end_time": end_time.isoformat()}
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return []

    async def mark_reminder_sent(self, appointment_id: str, reminder_type: str):
        try:
            await self.client.put(f"/internal/{appointment_id}/reminder-sent", json={"type": reminder_type})
        except Exception:
            pass
