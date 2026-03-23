from dataclasses import dataclass

from uuid_extension import UUID7


@dataclass
class Doctor:
    user_id: UUID7  # Same as Auth User ID
    full_name: str
    specialty_id: UUID7 | None = None
    title: str | None = None
    experience_years: int = 0
    auto_confirm: bool = True
    confirmation_timeout_minutes: int = 15

    def __post_init__(self):
        if not self.full_name:
            raise ValueError("Doctor full name is required")
        if self.experience_years < 0:
            raise ValueError("Experience years cannot be negative")
        if self.confirmation_timeout_minutes <= 0:
            raise ValueError("Confirmation timeout must be greater than 0")
