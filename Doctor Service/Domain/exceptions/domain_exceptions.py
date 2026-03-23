class DomainException(Exception):
    """Base exception for Doctor Service Domain"""


class SpecialtyAlreadyExistsException(DomainException):
    def __init__(self, name: str):
        super().__init__(f"Specialty with name '{name}' already exists")


class DoctorNotFoundException(DomainException):
    def __init__(self, doctor_id):
        super().__init__(f"Doctor with ID {doctor_id} not found")


class SpecialtyNotFoundException(DomainException):
    def __init__(self, specialty_id):
        super().__init__(f"Specialty with ID {specialty_id} not found")


class ScheduleConflictException(DomainException):
    def __init__(self, message: str = "Schedule conflict detected"):
        super().__init__(message)
