from pydantic import BaseModel, BeforeValidator
from uuid import UUID
from datetime import date, time
from typing import Annotated, Any
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus

# Convert UUID7 to string
def coerce_to_uuid_str(v: Any) -> Any:
    from uuid_extension import UUID7
    if hasattr(v, '__class__') and v.__class__.__name__ == 'UUID7':
        return str(v)
    return v

SafeUUID = Annotated[UUID, BeforeValidator(coerce_to_uuid_str)]

class CreateAppointmentRequest(BaseModel):
    patient_id: SafeUUID
    doctor_id: SafeUUID
    specialty_id: SafeUUID
    appointment_date: date
    start_time: time
    appointment_type: str = "general"
    chief_complaint: str | None = None
    note_for_doctor: str | None = None

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

    class Config:
        from_attributes = True


class DeclineAppointmentRequest(BaseModel):
    reason: str | None = None


class CancelAppointmentRequest(BaseModel):
    reason: str | None = None


class RescheduleAppointmentRequest(BaseModel):
    new_date: date
    new_time: time


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
