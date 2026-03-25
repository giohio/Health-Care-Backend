from healthai_events.exceptions import NonRetryableError


class AppointmentDomainError(Exception):
    """Base for all appointment domain errors."""


class SlotNotAvailableError(AppointmentDomainError, NonRetryableError):
    """Raised when the requested slot is already taken."""


class InvalidStatusTransitionError(AppointmentDomainError, NonRetryableError):
    """Raised when trying an invalid status transition."""


class AppointmentNotFoundError(AppointmentDomainError, NonRetryableError):
    pass


class UnauthorizedActionError(AppointmentDomainError, NonRetryableError):
    """Raised when the caller does not own the appointment action."""


class DoctorScheduleUnavailableError(AppointmentDomainError):
    """Raised when schedule data cannot be fetched from Doctor Service."""


class NoDoctorAvailableException(DoctorScheduleUnavailableError):
    def __init__(self):
        super().__init__("No doctors are available for the selected specialty and time.")


class AppointmentNotFoundException(AppointmentNotFoundError):
    def __init__(self):
        super().__init__("Appointment not found.")
