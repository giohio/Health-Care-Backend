from enum import Enum


class RecordSource(str, Enum):
    DOCTOR = "doctor"
    AI_ASSISTED = "ai_assisted"
