import json
import logging
from datetime import datetime, time, timedelta

from Application.dtos import AvailableSlotItem, AvailableSlotsResponse
from Application.use_cases._helpers import add_minutes

logger = logging.getLogger(__name__)


def _normalize_cached_payload(cached):
    if isinstance(cached, str):
        return json.loads(cached)
    return cached


class GetAvailableSlotsUseCase:
    def __init__(self, appointment_repo, doctor_client, cache=None):
        self.appointment_repo = appointment_repo
        self.doctor_client = doctor_client
        self.cache = cache

    async def execute(
        self, doctor_id, appointment_date, specialty_id, appointment_type: str, service_id: str = None
    ) -> AvailableSlotsResponse:
        if self.cache:
            key = f"slots:{doctor_id}:{appointment_date}:{specialty_id}:{appointment_type}:{service_id or ''}"
            cached = await self.cache.get(key)
            if cached:
                return AvailableSlotsResponse.model_validate(_normalize_cached_payload(cached))
        enhanced = await self.doctor_client.get_enhanced_schedule(str(doctor_id), str(appointment_date))

        if not enhanced or not enhanced.get("working_hours"):
            schedule = await self.doctor_client.get_schedule(str(doctor_id))
            if not schedule:
                return AvailableSlotsResponse(
                    date=appointment_date,
                    doctor_id=doctor_id,
                    duration_minutes=30,
                    slots=[],
                    error="Doctor schedule is unavailable",
                )
            return await self._legacy_slot_generation(
                doctor_id, appointment_date, specialty_id, appointment_type, schedule
            )

        duration, buffer = await self._get_duration_and_buffer(specialty_id, appointment_type, service_id, enhanced)

        max_patients = enhanced["working_hours"][0].get("max_patients", 20) if enhanced["working_hours"] else 20
        confirmed_count = await self.appointment_repo.count_confirmed_on_date(doctor_id, appointment_date)
        if confirmed_count >= max_patients:
            return AvailableSlotsResponse(
                date=appointment_date,
                doctor_id=doctor_id,
                duration_minutes=duration,
                slots=[],
                error="Doctor has reached maximum patients for this date",
            )

        booked = await self.appointment_repo.get_booked_slots(doctor_id, appointment_date)
        windows = []
        for wh in enhanced["working_hours"]:
            windows.extend(self._extract_working_windows(wh))

        items = self._generate_slots(appointment_date, windows, duration, duration + buffer, booked)

        result = AvailableSlotsResponse(
            date=appointment_date, doctor_id=doctor_id, duration_minutes=duration, slots=items
        )
        if self.cache:
            await self.cache.setex(key, 120, result.model_dump(mode="json"))
        return result

    async def _get_duration_and_buffer(self, specialty_id, appointment_type, service_id, enhanced):
        if service_id and enhanced.get("services"):
            for svc in enhanced["services"]:
                if svc.get("id") == service_id:
                    return svc.get("duration_minutes", 30), 0

        config = await self.doctor_client.get_type_config(str(specialty_id), appointment_type)
        duration = (config or {}).get("duration_minutes", 30)
        buffer = 5
        return duration, buffer

    def _generate_slots(self, appointment_date, windows, duration, step, booked):
        items = []
        for start_t, end_t in windows:
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
        return items

    def _extract_working_windows(self, working_hours: dict) -> list[tuple[time, time]]:
        start_t = time.fromisoformat(working_hours["start_time"])
        end_t = time.fromisoformat(working_hours["end_time"])
        break_start = working_hours.get("break_start")
        break_end = working_hours.get("break_end")

        if break_start and break_end:
            break_start_t = time.fromisoformat(break_start)
            break_end_t = time.fromisoformat(break_end)
            return [(start_t, break_start_t), (break_end_t, end_t)]
        return [(start_t, end_t)]

    async def _legacy_slot_generation(self, doctor_id, appointment_date, specialty_id, appointment_type, schedule):
        config = await self.doctor_client.get_type_config(str(specialty_id), appointment_type)
        duration = (config or {}).get("duration_minutes", 30)
        buffer_minutes = (config or {}).get("buffer_minutes", 5)

        windows = self._extract_schedule_window(schedule)
        if not windows:
            return AvailableSlotsResponse(
                date=appointment_date,
                doctor_id=doctor_id,
                duration_minutes=duration,
                slots=[],
                error="Doctor is not working in requested date",
            )

        booked = await self.appointment_repo.get_booked_slots(doctor_id, appointment_date)
        step = duration + buffer_minutes
        items = self._generate_slots(appointment_date, windows, duration, step, booked)

        return AvailableSlotsResponse(
            date=appointment_date,
            doctor_id=doctor_id,
            duration_minutes=duration,
            slots=items,
        )

    @staticmethod
    def _extract_schedule_window(schedule: any) -> list[tuple[time, time]]:
        if not schedule:
            return []

        windows = []
        items = []
        if isinstance(schedule, list):
            items = schedule
        elif isinstance(schedule, dict):
            items = schedule.get("working_hours", [])
            if not items and schedule.get("start_time") and schedule.get("end_time"):
                items = [schedule]

        for item in items:
            try:
                st = item.get("start_time")
                et = item.get("end_time")
                if st and et:
                    windows.append((time.fromisoformat(st), time.fromisoformat(et)))
                else:
                    logger.warning(f"Skipping malformed schedule item: {item}")
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to parse schedule time for item {item}: {e}")
                # If we're being strict, we could raise here. For now, we log and continue
                # but we could also raise a specific exception if needed.
                continue

        if items and not windows:
            logger.error("Parsed schedule is empty despite having items. Data might be corrupted.")

        return windows
