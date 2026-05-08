from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from uuid_extension import UUID7, uuid7


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class InsuranceType(str, Enum):
    BHYT_PUBLIC = "BHYT_PUBLIC"
    PRIVATE = "PRIVATE"
    NONE = "NONE"


@dataclass
class VitalSigns:
    height_cm: float | None = None
    weight_kg: float | None = None
    blood_pressure: str | None = None
    heart_rate_bpm: int | None = None

    @classmethod
    def from_value(cls, value: "VitalSigns | dict | None") -> "VitalSigns | None":
        if value is None or isinstance(value, cls):
            return value
        return cls(**value)


@dataclass
class EmergencyContact:
    name: str | None = None
    relationship: str | None = None
    phone: str | None = None
    email: str | None = None

    @classmethod
    def from_value(cls, value: "EmergencyContact | dict | None") -> "EmergencyContact | None":
        if value is None or isinstance(value, cls):
            return value
        return cls(**value)


@dataclass
class InsuranceInfo:
    type: InsuranceType = InsuranceType.NONE
    provider: str | None = None
    policy_id: str | None = None
    expiry_date: date | None = None
    card_number: str | None = None
    registered_hospital: str | None = None

    @classmethod
    def from_value(cls, value: "InsuranceInfo | dict | None") -> "InsuranceInfo | None":
        if value is None or isinstance(value, cls):
            return value
        raw_type = value.get("type", InsuranceType.NONE)
        insurance_type = raw_type if isinstance(raw_type, InsuranceType) else InsuranceType(str(raw_type))
        expiry_date = value.get("expiry_date")
        if isinstance(expiry_date, str):
            expiry_date = date.fromisoformat(expiry_date)
        return cls(
            type=insurance_type,
            provider=value.get("provider"),
            policy_id=value.get("policy_id"),
            expiry_date=expiry_date,
            card_number=value.get("card_number"),
            registered_hospital=value.get("registered_hospital"),
        )


@dataclass
class PatientProfile:
    user_id: UUID7
    full_name: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    phone_number: str | None = None
    address: str | None = None
    avatar_url: str | None = None
    profile_photo_url: str | None = None
    vital_signs: VitalSigns | None = None
    emergency_contact: EmergencyContact | None = None
    insurance: InsuranceInfo | None = None
    id: UUID7 = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        self.vital_signs = VitalSigns.from_value(self.vital_signs)
        self.emergency_contact = EmergencyContact.from_value(self.emergency_contact)
        self.insurance = InsuranceInfo.from_value(self.insurance)
        self._sync_photo_urls()

    def _sync_photo_urls(self):
        if self.profile_photo_url and not self.avatar_url:
            self.avatar_url = self.profile_photo_url
        elif self.avatar_url and not self.profile_photo_url:
            self.profile_photo_url = self.avatar_url

    def update_profile(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                if key == "vital_signs":
                    value = VitalSigns.from_value(value)
                elif key == "emergency_contact":
                    value = EmergencyContact.from_value(value)
                elif key == "insurance":
                    value = InsuranceInfo.from_value(value)
                setattr(self, key, value)
        self._sync_photo_urls()
        self.updated_at = datetime.now()
