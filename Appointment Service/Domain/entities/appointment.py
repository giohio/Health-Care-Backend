from dataclasses import dataclass
from uuid_extension import UUID7
from datetime import date, time
from Domain.value_objects.appointment_status import AppointmentStatus
from Domain.value_objects.payment_status import PaymentStatus

@dataclass
class Appointment:
    id: UUID7
    patient_id: UUID7
    doctor_id: UUID7
    specialty_id: UUID7
    appointment_date: date
    start_time: time
    end_time: time
    status: AppointmentStatus = AppointmentStatus.PENDING
    payment_status: PaymentStatus = PaymentStatus.UNPAID

    def __post_init__(self):
        # Normalize to naive time objects to prevent timezone offset comparison issues
        if self.start_time.tzinfo is not None:
            self.start_time = self.start_time.replace(tzinfo=None)
        if self.end_time.tzinfo is not None:
            self.end_time = self.end_time.replace(tzinfo=None)

        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        
        if self.appointment_date < date.today():
            # In a real app, we'd allow historic data migration, 
            # but for new bookings this is a good invariant.
            pass 
