from healthai_events.exceptions import NonRetryableError


class AppointmentError(Exception):
    pass


class SlotNotAvailableError(AppointmentError, NonRetryableError):
    """Slot already booked/locked and should not be retried immediately."""


class DoctorNotAvailableError(AppointmentError):
    """No available doctor found for requested slot."""


class AppointmentNotFoundError(AppointmentError):
    pass


class InvalidAppointmentStatusError(AppointmentError):
    """Invalid state transition for appointment status."""
