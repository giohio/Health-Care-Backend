from enum import Enum


class AppointmentStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class CancelledBy(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    SYSTEM = "system"
    ADMIN = "admin"


VALID_TRANSITIONS = {
    AppointmentStatus.PENDING_PAYMENT: [
        AppointmentStatus.PENDING,
        AppointmentStatus.CANCELLED,
    ],
    AppointmentStatus.PENDING: [
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.DECLINED,
        AppointmentStatus.CANCELLED,
    ],
    AppointmentStatus.CONFIRMED: [
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
    ],
}


def can_transition(
    current: AppointmentStatus,
    target: AppointmentStatus,
) -> bool:
    """Return whether the requested transition is allowed by domain rules."""
    return target in VALID_TRANSITIONS.get(current, [])
