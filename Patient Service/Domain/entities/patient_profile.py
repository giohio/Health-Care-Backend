from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from uuid_extension import UUID7, uuid7


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


@dataclass
class PatientProfile:
    user_id: UUID7
    full_name: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    phone_number: str | None = None
    address: str | None = None
    avatar_url: str | None = None
    id: UUID7 = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def update_profile(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()
