from dataclasses import dataclass
from uuid_extension import UUID7
from datetime import time
from Domain.value_objects.day_of_week import DayOfWeek

@dataclass
class DoctorSchedule:
    id: UUID7
    doctor_id: UUID7
    day_of_week: DayOfWeek
    start_time: time
    end_time: time
    slot_duration_minutes: int = 30

    def __post_init__(self):
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        if self.slot_duration_minutes <= 0:
            raise ValueError("Slot duration must be positive")
