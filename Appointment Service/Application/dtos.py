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
    specialty_id: SafeUUID
    appointment_date: date
    start_time: time

class AppointmentResponse(BaseModel):
    id: SafeUUID
    patient_id: SafeUUID
    doctor_id: SafeUUID
    specialty_id: SafeUUID
    appointment_date: date
    start_time: time
    end_time: time
    status: AppointmentStatus
    payment_status: PaymentStatus

    class Config:
        from_attributes = True
