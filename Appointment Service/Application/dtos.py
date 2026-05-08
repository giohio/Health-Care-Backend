import re
from datetime import date, datetime, time
from typing import Annotated, Any
from uuid import UUID

from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_serializer, model_validator
from pydantic.json_schema import SkipJsonSchema


# Convert UUID7 to string
def coerce_to_uuid_str(v: Any) -> Any:
    if hasattr(v, "__class__") and v.__class__.__name__ == "UUID7":
        return str(v)
    return v


SafeUUID = Annotated[UUID, BeforeValidator(coerce_to_uuid_str)]


class CreateAppointmentRequest(BaseModel):
    patient_id: SkipJsonSchema[SafeUUID | None] = None  # injected by Kong, hidden from Swagger
    doctor_id: SafeUUID
    specialty_id: SafeUUID
    appointment_date: date
    start_time: time
    appointment_type: str = "general"
    chief_complaint: str | None = None
    note_for_doctor: str | None = None
    # AI Triage referral fields
    triage_session_id: SkipJsonSchema[SafeUUID | None] = None
    ai_referred: bool = False
    urgency_level: str | None = None
    referred_by_doctor_id: SkipJsonSchema[SafeUUID | None] = None


class AppointmentResponse(BaseModel):
    id: SafeUUID
    patient_id: SafeUUID
    doctor_id: SafeUUID
    specialty_id: SafeUUID
    appointment_date: date
    start_time: time
    end_time: time
    appointment_type: str
    chief_complaint: str | None = None
    note_for_doctor: str | None = None
    status: AppointmentStatus
    payment_status: PaymentStatus
    queue_number: int | None = None
    consultation_fee: int = 0
    confirmed_at: datetime | None = None
    started_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_by: str | None = None          # "doctor" | "patient" | "admin"
    cancel_reason: str | None = None         # human-readable reason (stripped)
    redirect_department: str | None = None   # department to re-book at after decline
    # AI Triage referral fields
    triage_session_id: SafeUUID | None = None
    ai_referred: bool = False
    urgency_level: str | None = None
    referred_by_doctor_id: SafeUUID | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _parse_redirect_from_cancel_reason(self) -> "AppointmentResponse":
        """
        The backend encodes redirect_department into cancel_reason as
        '[redirect:DeptName] free-text reason'.  Extract both parts so the
        FE can consume them independently without string-parsing.
        """
        raw = self.cancel_reason
        if raw:
            m = re.match(r"^\[redirect:([^\]]+)\]\s*(.*)", raw)
            if m:
                self.redirect_department = m.group(1)
                self.cancel_reason = m.group(2) or None
        return self

    @field_serializer("start_time", "end_time")
    def serialize_time(self, v: time, _info):
        return v.strftime("%H:%M")


class DeclineAppointmentRequest(BaseModel):
    reason: str | None = None
    redirect_department: str | None = None
    """Optional department to redirect the patient to after decline."""


class CancelAppointmentRequest(BaseModel):
    reason: str | None = None


class RescheduleAppointmentRequest(BaseModel):
    new_date: date
    new_time: time


class AdjustAppointmentRequest(BaseModel):
    duration_minutes: int
    consultation_fee: int | None = None


class AvailableSlotItem(BaseModel):
    start_time: time
    end_time: time
    is_available: bool
    reason: str | None = None


class AvailableSlotsResponse(BaseModel):
    date: date
    doctor_id: SafeUUID
    duration_minutes: int
    slots: list[AvailableSlotItem]
    error: str | None = None


class DoctorQueueItemResponse(BaseModel):
    appointment_id: SafeUUID
    patient_id: SafeUUID
    patient_name: str | None = None
    appointment_date: date
    start_time: time
    end_time: time
    status: AppointmentStatus
    queue_number: int | None = None
    appointment_type: str
    chief_complaint: str | None = None
    lab_readiness: dict[str, Any] | None = None
    # AI Triage referral fields
    ai_referred: bool = False
    urgency_level: str | None = None
