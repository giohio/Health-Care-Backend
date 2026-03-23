from datetime import date, datetime
from typing import Any
from uuid import UUID

from Domain.entities.patient_health_background import BloodType
from Domain.entities.patient_profile import Gender
from pydantic import BaseModel, ConfigDict


class PatientProfileBase(BaseModel):
    full_name: str | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    phone_number: str | None = None
    address: str | None = None
    avatar_url: str | None = None


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
