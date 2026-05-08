class ClinicalDomainError(Exception):
    """Base for all clinical domain errors."""


class DiagnosisNotFoundError(ClinicalDomainError):
    def __init__(self):
        super().__init__("Diagnosis not found.")


class MedicationNotFoundError(ClinicalDomainError):
    def __init__(self):
        super().__init__("Medication not found.")


class ClinicalNoteNotFoundError(ClinicalDomainError):
    def __init__(self):
        super().__init__("Clinical note not found.")


class InvalidMedicationStatusTransitionError(ClinicalDomainError):
    """Raised when a medication status transition is not allowed."""

    def __init__(self, current: str, requested: str):
        super().__init__(
            f"Cannot transition medication from '{current}' to '{requested}'."
        )


class InvalidDiagnosisStatusTransitionError(ClinicalDomainError):
    """Raised when a diagnosis status transition is not allowed."""

    def __init__(self, current: str, requested: str):
        super().__init__(
            f"Cannot transition diagnosis from '{current}' to '{requested}'."
        )


class UnauthorizedClinicalActionError(ClinicalDomainError):
    """Raised when the caller does not have permission to perform a clinical action."""

    def __init__(self):
        super().__init__("Unauthorized: you do not have permission to perform this clinical action.")
