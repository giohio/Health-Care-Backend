from dataclasses import dataclass
from enum import Enum
from typing import Any

from uuid_extension import UUID7


class BloodType(str, Enum):
    A = "A"
    B = "B"
    AB = "AB"
    O = "O"  # noqa


@dataclass
class PatientHealthBackground:
    patient_id: UUID7
    blood_type: BloodType | None = None
    height_cm: int | None = None
    weight_kg: float | None = None
    allergies: Any | None = None  # Text or JSONB
    chronic_conditions: Any | None = None  # Text or JSONB

    def update_background(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
