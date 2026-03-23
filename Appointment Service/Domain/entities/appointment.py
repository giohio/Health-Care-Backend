from dataclasses import dataclass
from datetime import date, datetime, time

from Domain.value_objects.appointment_status import AppointmentStatus, can_transition
from Domain.value_objects.payment_status import PaymentStatus
from uuid_extension import UUID7


@dataclass
class Appointment:
    id: UUID7
    patient_id: UUID7
    doctor_id: UUID7
    specialty_id: UUID7
    appointment_date: date
    start_time: time
    end_time: time
    appointment_type: str = "general"
    chief_complaint: str | None = None
    note_for_doctor: str | None = None
    status: AppointmentStatus = AppointmentStatus.PENDING_PAYMENT
    payment_status: PaymentStatus = PaymentStatus.PROCESSING
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_by: str | None = None
    cancelled_by_user_id: UUID7 | None = None
    cancel_reason: str | None = None
    queue_number: int | None = None
    reminder_24h_sent: bool = False
    reminder_1h_sent: bool = False

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

    def can_be_confirmed_by(self, doctor_id: UUID7) -> bool:
        """Only the assigned doctor can confirm a pending appointment."""
        return self.doctor_id == doctor_id and self.status == AppointmentStatus.PENDING

    def can_be_cancelled_by(self, user_id: UUID7, user_role: str) -> bool:
        """Check whether the given caller is allowed to cancel this appointment."""
        if user_role == "admin":
            return True
        if user_role == "patient":
            return self.patient_id == user_id
        if user_role == "doctor":
            return self.doctor_id == user_id
        return False

    def can_be_rescheduled_by(self, patient_id: UUID7) -> bool:
        """Only the owner patient can reschedule pending/confirmed appointments."""
        return self.patient_id == patient_id and self.status in (
            AppointmentStatus.PENDING,
            AppointmentStatus.CONFIRMED,
        )

    def can_transition_to(self, target: AppointmentStatus) -> bool:
        """Wrapper around value-object transition rules."""
        return can_transition(self.status, target)
