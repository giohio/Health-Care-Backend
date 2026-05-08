from enum import Enum


class MedicationStatus(str, Enum):
    ACTIVE = "active"
    STOPPED = "stopped"
    COMPLETED = "completed"
