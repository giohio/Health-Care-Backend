class AppointmentDomainException(Exception):
    pass

class NoDoctorAvailableException(AppointmentDomainException):
    def __init__(self):
        super().__init__("No doctors are available for the selected specialty and time.")

class AppointmentNotFoundException(AppointmentDomainException):
    def __init__(self):
        super().__init__("Appointment not found.")
