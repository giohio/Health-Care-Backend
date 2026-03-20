from dataclasses import dataclass
from datetime import time

@dataclass(frozen=True)
class ScheduleTime:
    start_time: time
    end_time: time

    def __post_init__(self):
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")

    def is_overlapping(self, other: 'ScheduleTime') -> bool:
        return not (self.end_time <= other.start_time or self.start_time >= other.end_time)
