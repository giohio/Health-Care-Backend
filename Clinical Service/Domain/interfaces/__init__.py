from Domain.interfaces.clinical_note_repository import IClinicalNoteRepository
from Domain.interfaces.diagnosis_repository import IDiagnosisRepository
from Domain.interfaces.medication_repository import IMedicationRepository
from Domain.interfaces.patient_service_client import IPatientServiceClient
from Domain.interfaces.vaccination_repository import IVaccinationRepository

__all__ = [
    "IClinicalNoteRepository",
    "IDiagnosisRepository",
    "IMedicationRepository",
    "IPatientServiceClient",
    "IVaccinationRepository",
]
