from datetime import date, timedelta

from Domain.interfaces.appointment_repository import IAppointmentRepository
from uuid_extension import UUID7


class GetAppointmentStatsUseCase:
    def __init__(self, appointment_repo: IAppointmentRepository):
        self.appointment_repo = appointment_repo

    async def execute(self, doctor_id: UUID7, range_type: str = "today"):
        today = date.today()
        if range_type == "week":
            date_from = today
            date_to = today + timedelta(days=7)
        elif range_type == "month":
            date_from = today.replace(day=1)
            date_to = (date_from + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        else:
            date_from = date_to = today

        appointments = await self.appointment_repo.list_by_doctor(doctor_id, date_from, date_to)

        stats = {
            "total_appointments": len(appointments),
            "booked_appointments": sum(
                1 for a in appointments if a.status.value in ("PENDING", "PENDING_PAYMENT", "CONFIRMED")
            ),
            "pending_appointments": sum(1 for a in appointments if a.status.value == "PENDING"),
            "confirmed_appointments": sum(1 for a in appointments if a.status.value == "CONFIRMED"),
            "completed_appointments": sum(1 for a in appointments if a.status.value == "COMPLETED"),
            "cancelled_appointments": sum(1 for a in appointments if a.status.value == "CANCELLED"),
        }
        return stats
