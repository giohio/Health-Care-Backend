from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from uuid_extension import UUID7, uuid7


class UserRole(StrEnum):
    ADMIN = "admin"
    PATIENT = "patient"
    DOCTOR = "doctor"


@dataclass
class User:
    email: str
    hashed_password: str
    role: UserRole

    id: UUID7 = field(default_factory=uuid7)

    is_active: bool = True
    is_deleted: bool = False
    is_email_verified: bool = True
    is_profile_completed: bool = False

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    deleted_at: datetime | None = None

    def can_login(self) -> bool:
        return self.is_active and not self.is_deleted

    def record_login(self):
        self.updated_at = datetime.now()
