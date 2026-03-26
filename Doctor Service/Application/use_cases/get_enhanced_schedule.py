from datetime import date

from uuid_extension import UUID7


class GetEnhancedScheduleUseCase:
    def __init__(self, availability_repo, day_off_repo, service_offering_repo):
        self.availability_repo = availability_repo
        self.day_off_repo = day_off_repo
        self.service_offering_repo = service_offering_repo

    async def execute(self, doctor_id: UUID7, target_date: date):
        day_of_week = target_date.weekday()
        is_day_off = await self.day_off_repo.is_day_off(doctor_id, target_date)
        availability = await self.availability_repo.get_by_doctor_and_day(doctor_id, day_of_week)

        if not availability:
            return {
                "doctor_id": str(doctor_id),
                "date": str(target_date),
                "is_day_off": is_day_off,
                "working_hours": [],
                "services": [],
            }
        services = await self.service_offering_repo.list_by_doctor(doctor_id)

        working_hours = []
        if not is_day_off and availability:
            for avail in availability:
                hours = {
                    "start_time": str(avail.start_time),
                    "end_time": str(avail.end_time),
                    "max_patients": avail.max_patients,
                }
                if avail.break_start and avail.break_end:
                    hours["break_start"] = str(avail.break_start)
                    hours["break_end"] = str(avail.break_end)
                working_hours.append(hours)

        return {
            "doctor_id": str(doctor_id),
            "date": str(target_date),
            "is_day_off": is_day_off,
            "working_hours": working_hours,
            "services": [
                {"id": str(s.id), "service_name": s.service_name, "duration_minutes": s.duration_minutes, "fee": s.fee}
                for s in services
                if s.is_active
            ],
        }
