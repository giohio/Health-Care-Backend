from datetime import date, datetime
from typing import Any
from uuid import UUID

from Domain.entities.patient_health_background import BloodType
from Domain.entities.patient_profile import Gender, InsuranceType
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class VitalSignsPayload(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    blood_pressure: str | None = None
    heart_rate_bpm: int | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("height_cm", "weight_kg")
    @classmethod
    def positive_float(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("Value must be greater than zero")
        return v

    @field_validator("heart_rate_bpm")
    @classmethod
    def positive_heart_rate(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("Heart rate must be greater than zero")
        return v


class EmergencyContactPayload(BaseModel):
    name: str | None = None
    relationship: str | None = None
    phone: str | None = None
    email: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str | None) -> str | None:
        if v is not None and "@" not in v:
            raise ValueError("Invalid email address")
        return v


class InsurancePayload(BaseModel):
    type: InsuranceType = InsuranceType.NONE
    provider: str | None = None
    policy_id: str | None = None
    expiry_date: date | None = None
    card_number: str | None = None
    registered_hospital: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_by_type(self):
        if self.expiry_date is not None and self.expiry_date < date.today():
            raise ValueError("Insurance expiry date cannot be in the past")
        if self.type == InsuranceType.BHYT_PUBLIC:
            if not self.card_number or not self.registered_hospital:
                raise ValueError("BHYT_PUBLIC requires card_number and registered_hospital")
        if self.type == InsuranceType.PRIVATE:
            if not self.provider or not self.policy_id:
                raise ValueError("PRIVATE insurance requires provider and policy_id")
        return self


class PatientProfileBase(BaseModel):
    full_name: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    phone_number: str | None = None
    address: str | None = None
    avatar_url: str | None = None
    profile_photo_url: str | None = None
    vital_signs: VitalSignsPayload | None = None
    emergency_contact: EmergencyContactPayload | None = None
    insurance: InsurancePayload | None = None

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_in_future(cls, v: date | None) -> date | None:
        if v is not None and v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v

    @model_validator(mode="after")
    def sync_photo_fields(self):
        if self.profile_photo_url and not self.avatar_url:
            self.avatar_url = self.profile_photo_url
        elif self.avatar_url and not self.profile_photo_url:
            self.profile_photo_url = self.avatar_url
        return self


class ProfileUpdate(PatientProfileBase):
    pass


class PatientProfileResponse(PatientProfileBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HealthBackgroundBase(BaseModel):
    blood_type: BloodType | None = None
    height_cm: int | None = None
    weight_kg: float | None = None
    allergies: Any | None = None  # Text or JSON data
    chronic_conditions: Any | None = None


class HealthUpdate(HealthBackgroundBase):
    pass


class PatientHealthResponse(HealthBackgroundBase):
    patient_id: UUID

    model_config = ConfigDict(from_attributes=True)


class PatientFullContextResponse(BaseModel):
    profile: PatientProfileResponse
    health_background: PatientHealthResponse

    model_config = ConfigDict(from_attributes=True)


class PatientPhotoUploadResponse(BaseModel):
    profile_photo_url: str


class PatientSummaryResponse(BaseModel):
    """
    Subset of patient profile returned to doctors/admins.
    Contains only clinical-relevant fields — no sensitive auth information.
    """

    user_id: UUID
    full_name: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    phone_number: str | None = None
    avatar_url: str | None = None
    blood_type: BloodType | None = None
    height_cm: int | None = None
    weight_kg: float | None = None
    allergies: Any | None = None
    chronic_conditions: Any | None = None
    vital_signs: VitalSignsPayload | None = None

    model_config = ConfigDict(from_attributes=True)
