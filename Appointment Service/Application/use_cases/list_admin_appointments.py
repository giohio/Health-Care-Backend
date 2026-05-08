from datetime import date, timedelta
from typing import Any

from Domain.interfaces.appointment_repository import IAppointmentRepository
from infrastructure.clients.doctor_service_client import DoctorServiceClient


class ListAdminAppointmentsUseCase:
    def __init__(self, appointment_repo: IAppointmentRepository, doctor_client: DoctorServiceClient):
        self.appointment_repo = appointment_repo
        self._doctor_client = doctor_client

    def _resolve_period(self, range_type: str, date_from: date | None, date_to: date | None) -> tuple[date, date]:
        if date_from and date_to:
            return date_from, date_to
        today = date.today()
        if range_type == "today":
            return today, today
        elif range_type == "week":
            return today - timedelta(days=6), today
        elif range_type == "quarter":
            return today - timedelta(days=89), today
        return today - timedelta(days=29), today  # month

    async def execute(
        self,
        range_type: str = "month",
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        doctor_id: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> dict[str, Any]:
        df, dt = self._resolve_period(range_type, date_from, date_to)
        appointments, total = await self.appointment_repo.list_filtered(
            date_from=df,
            date_to=dt,
            status=status,
            doctor_id=doctor_id,
            page=page,
            limit=limit,
        )

        # Enrich with specialty names from doctor service
        if appointments and self._doctor_client:
            try:
                specialties = await self._doctor_client.get_specialties()
                name_map = {str(s["id"]): s["name"] for s in specialties}
                for appt in appointments:
                    sid = appt.get("specialty_id")
                    appt["specialty_name"] = name_map.get(sid, sid) if sid else None
            except Exception:
                for appt in appointments:
                    appt["specialty_name"] = appt.get("specialty_id")

        total_pages = (total + limit - 1) // limit if total > 0 else 1
        return {
            "status": "success",
            "data": {
                "appointments": appointments,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "total_pages": total_pages,
                },
            },
        }
