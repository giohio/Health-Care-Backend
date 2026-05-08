"""Shared test helpers and fixtures for clinical_service unit tests."""
import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio

from Domain.entities.clinical_note import ClinicalNote
from Domain.entities.diagnosis import Diagnosis
from Domain.entities.medication import Medication
from Domain.entities.vaccination import Vaccination
from Domain.interfaces.clinical_note_repository import IClinicalNoteRepository
from Domain.interfaces.diagnosis_repository import IDiagnosisRepository
from Domain.interfaces.medication_repository import IMedicationRepository
from Domain.interfaces.patient_service_client import IPatientServiceClient
from Domain.interfaces.vaccination_repository import IVaccinationRepository
from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.medication_status import MedicationStatus
from Domain.value_objects.note_type import NoteType
from Domain.value_objects.record_source import RecordSource
from Domain.value_objects.severity import Severity


# ---------------------------------------------------------------------------
# Fake repositories (in-memory)
# ---------------------------------------------------------------------------


class FakeDiagnosisRepo(IDiagnosisRepository):
    def __init__(self):
        self._store: Dict[uuid.UUID, Diagnosis] = {}

    async def save(self, diagnosis: Diagnosis) -> Diagnosis:
        self._store[diagnosis.id] = diagnosis
        return diagnosis

    async def get_by_id(self, diagnosis_id: uuid.UUID) -> Optional[Diagnosis]:
        return self._store.get(diagnosis_id)

    async def list_by_patient(
        self,
        patient_id: uuid.UUID,
        status: Optional[DiagnosisStatus] = None,
    ) -> List[Diagnosis]:
        results = [d for d in self._store.values() if d.patient_id == patient_id]
        if status is not None:
            results = [d for d in results if d.status == status]
        return sorted(results, key=lambda d: d.diagnosed_at, reverse=True)


class FakeMedicationRepo(IMedicationRepository):
    def __init__(self):
        self._store: Dict[uuid.UUID, Medication] = {}

    async def save(self, medication: Medication) -> Medication:
        self._store[medication.id] = medication
        return medication

    async def get_by_id(self, medication_id: uuid.UUID) -> Optional[Medication]:
        return self._store.get(medication_id)

    async def list_by_patient(
        self,
        patient_id: uuid.UUID,
        status: Optional[MedicationStatus] = None,
    ) -> List[Medication]:
        results = [m for m in self._store.values() if m.patient_id == patient_id]
        if status is not None:
            results = [m for m in results if m.status == status]
        return sorted(results, key=lambda m: m.start_date, reverse=True)


class FakeNoteRepo(IClinicalNoteRepository):
    def __init__(self):
        self._store: Dict[uuid.UUID, ClinicalNote] = {}

    async def save(self, note: ClinicalNote) -> ClinicalNote:
        self._store[note.id] = note
        return note

    async def get_by_id(self, note_id: uuid.UUID) -> Optional[ClinicalNote]:
        return self._store.get(note_id)

    async def list_by_patient(
        self,
        patient_id: uuid.UUID,
        appointment_id: Optional[uuid.UUID] = None,
    ) -> List[ClinicalNote]:
        results = [n for n in self._store.values() if n.patient_id == patient_id]
        if appointment_id is not None:
            results = [n for n in results if n.appointment_id == appointment_id]
        return results

    async def update_content(self, note_id: uuid.UUID, content: str) -> Optional[ClinicalNote]:
        note = self._store.get(note_id)
        if note is None:
            return None
        from dataclasses import replace
        updated = replace(note, content=content)
        self._store[note_id] = updated
        return updated


class FakeVaccinationRepo(IVaccinationRepository):
    def __init__(self):
        self._store: Dict[uuid.UUID, Vaccination] = {}

    async def save(self, vaccination: Vaccination) -> Vaccination:
        self._store[vaccination.id] = vaccination
        return vaccination

    async def list_by_patient(self, patient_id: uuid.UUID) -> List[Vaccination]:
        results = [v for v in self._store.values() if v.patient_id == patient_id]
        return sorted(results, key=lambda v: v.date_administered, reverse=True)


class FakePatientClient(IPatientServiceClient):
    def __init__(self, allergies=None, vitals=None):
        self._allergies: List[str] = allergies or []
        self._vitals: Optional[Dict[str, Any]] = vitals

    async def get_allergies(self, patient_id: uuid.UUID) -> List[str]:
        return self._allergies

    async def get_latest_vitals(self, patient_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        return self._vitals


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_diagnosis(**kwargs) -> Diagnosis:
    defaults = {
        "id": uuid.uuid4(),
        "patient_id": uuid.uuid4(),
        "doctor_id": uuid.uuid4(),
        "diagnosis_name": "Hypertension",
        "diagnosed_at": date(2025, 1, 15),
        "status": DiagnosisStatus.ACTIVE,
        "source": RecordSource.DOCTOR,
    }
    defaults.update(kwargs)
    return Diagnosis(**defaults)


def make_medication(**kwargs) -> Medication:
    defaults = {
        "id": uuid.uuid4(),
        "patient_id": uuid.uuid4(),
        "doctor_id": uuid.uuid4(),
        "drug_name": "Amlodipine",
        "start_date": date(2025, 1, 15),
        "status": MedicationStatus.ACTIVE,
    }
    defaults.update(kwargs)
    return Medication(**defaults)


def make_clinical_note(**kwargs) -> ClinicalNote:
    defaults = {
        "id": uuid.uuid4(),
        "patient_id": uuid.uuid4(),
        "doctor_id": uuid.uuid4(),
        "content": "Patient presents with elevated BP.",
        "note_type": NoteType.SOAP,
        "is_ai_generated": False,
    }
    defaults.update(kwargs)
    return ClinicalNote(**defaults)


def make_vaccination(**kwargs) -> Vaccination:
    defaults = {
        "id": uuid.uuid4(),
        "patient_id": uuid.uuid4(),
        "vaccine_name": "COVID-19",
        "date_administered": date(2025, 1, 15),
        "next_due_date": None,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return Vaccination(**defaults)
