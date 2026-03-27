from enum import Enum


class AppointmentStatus(str, Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


class CancelledBy(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    SYSTEM = "system"
    ADMIN = "admin"


VALID_TRANSITIONS = {
    AppointmentStatus.PENDING_PAYMENT: [
        AppointmentStatus.PENDING,
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.CANCELLED,
    ],
    AppointmentStatus.PENDING: [
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.DECLINED,
        AppointmentStatus.CANCELLED,
    ],
    AppointmentStatus.CONFIRMED: [
        AppointmentStatus.IN_PROGRESS,
        AppointmentStatus.COMPLETED,
        AppointmentStatus.CANCELLED,
        AppointmentStatus.NO_SHOW,
    ],
    AppointmentStatus.IN_PROGRESS: [
        AppointmentStatus.COMPLETED,
        AppointmentStatus.NO_SHOW,
    ],
}


def can_transition(
    current: AppointmentStatus,
    target: AppointmentStatus,
) -> bool:
    """Return whether the requested transition is allowed by domain rules."""
    return target in VALID_TRANSITIONS.get(current, [])
