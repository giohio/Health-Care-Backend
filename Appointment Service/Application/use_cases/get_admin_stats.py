from datetime import date, timedelta
from uuid import UUID

from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus


class GetAdminStatsUseCase:
    def __init__(self, appointment_repo: IAppointmentRepository, doctor_client=None):
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client

    def _resolve_period(
        self, range_type: str, date_from: date | None, date_to: date | None
    ) -> tuple[date, date]:
        if date_from and date_to:
            return date_from, date_to
        today = date.today()
        if range_type == "week":
            return today - timedelta(days=6), today
        elif range_type == "quarter":
            return today - timedelta(days=89), today
        else:  # month (default)
            return today - timedelta(days=29), today

    async def execute(
        self,
        range_type: str = "month",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        df, dt = self._resolve_period(range_type, date_from, date_to)
        appointments = await self.appointment_repo.list_all(df, dt)

        # Aggregate by status
        by_status: dict[str, int] = {
            "confirmed": 0,
            "completed": 0,
            "cancelled": 0,
            "pending": 0,
            "no_show": 0,
            "pending_payment": 0,
            "in_progress": 0,
            "declined": 0,
        }
        total_revenue = 0.0
        by_specialty_map: dict[str, dict] = {}  # specialty_name -> {count, revenue}

        # Fetch specialty names first so we can group by name
        name_map: dict[str, str] = {}  # specialty_id -> specialty_name
        if self.doctor_client:
            try:
                specialties = await self.doctor_client.get_specialties()
                name_map = {str(s["id"]): s["name"] for s in specialties}
            except Exception:
                pass  # fall back to specialty_id as name

        for appt in appointments:
            status_key = appt.status.value.lower()
            if status_key in by_status:
                by_status[status_key] += 1

            # Revenue: sum consultation_fee for PAID appointments
            if appt.payment_status == PaymentStatus.PAID:
                total_revenue += appt.consultation_fee or 0

            # Group by specialty name (resolved from name_map or fallback to id)
            sid = str(appt.specialty_id)
            key = name_map.get(sid, sid)
            if key not in by_specialty_map:
                by_specialty_map[key] = {"specialty_id": sid, "specialty_name": key, "count": 0, "revenue": 0.0}
            by_specialty_map[key]["count"] += 1
            if appt.payment_status == PaymentStatus.PAID:
                by_specialty_map[key]["revenue"] += appt.consultation_fee or 0

        total = len(appointments)
        completed = by_status["completed"]
        cancelled = by_status["cancelled"]
        no_show = by_status["no_show"]

        denominator = completed + no_show + cancelled
        completion_rate = round(completed / denominator * 100, 1) if denominator else 0.0
        cancellation_rate = round(cancelled / total * 100, 1) if total else 0.0

        return {
            "status": "success",
            "data": {
                "period": {"date_from": str(df), "date_to": str(dt)},
                "total_appointments": total,
                "total_revenue": total_revenue,
                "by_status": by_status,
                "by_specialty": list(by_specialty_map.values()),
                "completion_rate": completion_rate,
                "cancellation_rate": cancellation_rate,
            },
        }
