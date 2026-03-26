import httpx
from uuid_extension import UUID7


class AppointmentServiceClient:
    def __init__(self, base_url: str = "http://appointment_service:8000"):
        self.base_url = base_url

    async def has_completed_appointment(self, patient_id: UUID7, doctor_id: UUID7) -> bool:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/internal/has-completed",
                params={"patient_id": str(patient_id), "doctor_id": str(doctor_id)},
                timeout=10.0,
            )
            if response.status_code == 200:
                return response.json().get("has_completed", False)
            return False

    async def get_appointment(self, appointment_id: UUID7) -> dict | None:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/internal/appointments/{appointment_id}", timeout=10.0)
            if response.status_code == 200:
                return response.json()
            return None
