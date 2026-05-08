from datetime import date, timedelta

from Domain.interfaces.appointment_repository import IAppointmentRepository
from Domain.value_objects.payment_status import PaymentStatus


class GetAdminChartDataUseCase:
    def __init__(self, appointment_repo: IAppointmentRepository):
        self.appointment_repo = appointment_repo

    def _resolve_period(self, range_type: str) -> tuple[date, date]:
        today = date.today()
        if range_type == "week":
            return today - timedelta(days=6), today
        elif range_type == "quarter":
            return today - timedelta(days=89), today
        else:  # month
            return today - timedelta(days=29), today

    async def execute(self, range_type: str = "month", metric: str = "appointments") -> dict:
        date_from, date_to = self._resolve_period(range_type)
        appointments = await self.appointment_repo.list_all(date_from, date_to)

        # Build a zero-filled dict for every day in range
        delta = (date_to - date_from).days
        daily: dict[str, float] = {}
        for i in range(delta + 1):
            d = date_from + timedelta(days=i)
            daily[str(d)] = 0.0

        for appt in appointments:
            day_key = str(appt.appointment_date)
            if day_key not in daily:
                continue
            if metric == "revenue":
                if appt.payment_status == PaymentStatus.PAID:
                    daily[day_key] += appt.consultation_fee or 0
            else:  # appointments
                daily[day_key] += 1

        data_points = [
            {
                "date": d,
                "value": int(v) if metric == "appointments" else v,
                "label": f"{d[8:10]}/{d[5:7]}",
            }
            for d, v in sorted(daily.items())
        ]

        total = sum(p["value"] for p in data_points)
        peak = max(data_points, key=lambda p: p["value"]) if data_points else {"date": str(date_from), "value": 0}

        return {
            "status": "success",
            "data": {
                "metric": metric,
                "period": {"date_from": str(date_from), "date_to": str(date_to)},
                "data_points": data_points,
                "total": total,
                "peak_day": {"date": peak["date"], "value": peak["value"]},
            },
        }
