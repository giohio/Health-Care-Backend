from functools import lru_cache
from typing import Annotated

from Application.use_cases.add_diagnosis import AddDiagnosisUseCase
from Application.use_cases.clinical_notes import CreateClinicalNoteUseCase, ListClinicalNotesUseCase, UpdateClinicalNoteUseCase
from Application.use_cases.get_patient_summary import GetPatientSummaryUseCase
from Application.use_cases.list_diagnoses import ListDiagnosesUseCase
from Application.use_cases.list_medications import ListMedicationsUseCase
from Application.use_cases.list_vaccinations import ListVaccinationsUseCase
from Application.use_cases.prescribe_medication import PrescribeMedicationUseCase
from Application.use_cases.update_diagnosis import UpdateDiagnosisUseCase
from Application.use_cases.update_medication_status import UpdateMedicationStatusUseCase
from fastapi import Depends
from healthai_cache import CacheClient
from infrastructure.clients.patient_service_client import PatientServiceClient
from infrastructure.config import settings
from infrastructure.database.session import get_db
from infrastructure.repositories import (
    ClinicalNoteRepository,
    DiagnosisRepository,
    MedicationRepository,
    VaccinationRepository,
)
from sqlalchemy.ext.asyncio import AsyncSession


def get_db_session(session: Annotated[AsyncSession, Depends(get_db)]) -> AsyncSession:
    return session


@lru_cache()
def get_cache_client() -> CacheClient:
    return CacheClient.from_url(settings.REDIS_URL)


def get_diagnosis_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return DiagnosisRepository(session)


def get_medication_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return MedicationRepository(session)


def get_note_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return ClinicalNoteRepository(session)


def get_vaccination_repo(session: Annotated[AsyncSession, Depends(get_db_session)]):
    return VaccinationRepository(session)


def get_patient_client(cache: Annotated[CacheClient, Depends(get_cache_client)]):
    return PatientServiceClient(cache=cache)


# ---------------------------------------------------------------------------
# Use case factories
# ---------------------------------------------------------------------------


def get_patient_summary_use_case(
    diagnosis_repo: Annotated[DiagnosisRepository, Depends(get_diagnosis_repo)],
    medication_repo: Annotated[MedicationRepository, Depends(get_medication_repo)],
    patient_client: Annotated[PatientServiceClient, Depends(get_patient_client)],
):
    return GetPatientSummaryUseCase(diagnosis_repo, medication_repo, patient_client)


def get_list_diagnoses_use_case(
    diagnosis_repo: Annotated[DiagnosisRepository, Depends(get_diagnosis_repo)],
):
    return ListDiagnosesUseCase(diagnosis_repo)


def get_add_diagnosis_use_case(
    diagnosis_repo: Annotated[DiagnosisRepository, Depends(get_diagnosis_repo)],
):
    return AddDiagnosisUseCase(diagnosis_repo)


def get_update_diagnosis_use_case(
    diagnosis_repo: Annotated[DiagnosisRepository, Depends(get_diagnosis_repo)],
):
    return UpdateDiagnosisUseCase(diagnosis_repo)


def get_list_medications_use_case(
    medication_repo: Annotated[MedicationRepository, Depends(get_medication_repo)],
):
    return ListMedicationsUseCase(medication_repo)


def get_prescribe_medication_use_case(
    medication_repo: Annotated[MedicationRepository, Depends(get_medication_repo)],
):
    return PrescribeMedicationUseCase(medication_repo)


def get_update_medication_status_use_case(
    medication_repo: Annotated[MedicationRepository, Depends(get_medication_repo)],
):
    return UpdateMedicationStatusUseCase(medication_repo)


def get_create_note_use_case(
    note_repo: Annotated[ClinicalNoteRepository, Depends(get_note_repo)],
):
    return CreateClinicalNoteUseCase(note_repo)


def get_update_note_use_case(
    note_repo: Annotated[ClinicalNoteRepository, Depends(get_note_repo)],
):
    return UpdateClinicalNoteUseCase(note_repo)


def get_list_notes_use_case(
    note_repo: Annotated[ClinicalNoteRepository, Depends(get_note_repo)],
):
    return ListClinicalNotesUseCase(note_repo)


def get_list_vaccinations_use_case(
    vaccination_repo: Annotated[VaccinationRepository, Depends(get_vaccination_repo)],
):
    return ListVaccinationsUseCase(vaccination_repo)
