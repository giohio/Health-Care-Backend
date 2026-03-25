from datetime import datetime, time, timedelta

from Application.dtos import AvailableSlotItem, AvailableSlotsResponse
from Application.use_cases._helpers import add_minutes


class GetAvailableSlotsUseCase:
    def __init__(self, appointment_repo, doctor_client):
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client

    async def execute(self, doctor_id, appointment_date, specialty_id, appointment_type: str) -> AvailableSlotsResponse:
        config = await self.doctor_client.get_type_config(str(specialty_id), appointment_type)
        duration = (config or {}).get("duration_minutes", 30)
        buffer_minutes = (config or {}).get("buffer_minutes", 5)

        schedule = await self.doctor_client.get_schedule(str(doctor_id))
        if not schedule:
            return AvailableSlotsResponse(
                date=appointment_date,
                doctor_id=doctor_id,
                duration_minutes=duration,
                slots=[],
                error="Doctor schedule is unavailable",
            )

        day_slots = self._extract_schedule_window(schedule)
        if not day_slots:
            return AvailableSlotsResponse(
                date=appointment_date,
                doctor_id=doctor_id,
                duration_minutes=duration,
                slots=[],
                error="Doctor is not working in requested date",
            )

        booked = await self.appointment_repo.get_booked_slots(doctor_id, appointment_date)
        items = []

        step = duration + buffer_minutes
        for start_t, end_t in day_slots:
            cursor = datetime.combine(appointment_date, start_t)
            window_end = datetime.combine(appointment_date, end_t)
            while cursor + timedelta(minutes=duration) <= window_end:
                slot_start = cursor.time()
                slot_end = add_minutes(slot_start, duration)
                overlap = any(b_start < slot_end and b_end > slot_start for b_start, b_end in booked)
                items.append(
                    AvailableSlotItem(
                        start_time=slot_start,
                        end_time=slot_end,
                        is_available=not overlap,
                        reason="booked" if overlap else None,
                    )
                )
                cursor += timedelta(minutes=step)

        return AvailableSlotsResponse(
            date=appointment_date,
            doctor_id=doctor_id,
            duration_minutes=duration,
            slots=items,
        )

    @staticmethod
    def _extract_schedule_window(schedule: dict) -> list[tuple[time, time]]:
        windows = []
        for item in schedule.get("working_hours", []):
            try:
                start_t = time.fromisoformat(item["start_time"])
                end_t = time.fromisoformat(item["end_time"])
                windows.append((start_t, end_t))
            except Exception:
                continue
        if windows:
            return windows

        if schedule.get("start_time") and schedule.get("end_time"):
            try:
                return [
                    (
                        time.fromisoformat(schedule["start_time"]),
                        time.fromisoformat(schedule["end_time"]),
                    )
                ]
            except Exception:
                return []
        return []
