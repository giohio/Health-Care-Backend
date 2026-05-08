class ClinicalApplicationError(Exception):
    """Base for application-level errors in clinical_service."""


class DiagnosisNotFoundError(ClinicalApplicationError):
    def __init__(self):
        super().__init__("Diagnosis not found.")


class MedicationNotFoundError(ClinicalApplicationError):
    def __init__(self):
        super().__init__("Medication not found.")


class ClinicalNoteNotFoundError(ClinicalApplicationError):
    def __init__(self):
        super().__init__("Clinical note not found.")
