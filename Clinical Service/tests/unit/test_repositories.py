"""Unit tests for infrastructure repositories using mocked AsyncSession."""
import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from Domain.entities.diagnosis import Diagnosis
from Domain.entities.medication import Medication
from Domain.entities.clinical_note import ClinicalNote
from Domain.entities.vaccination import Vaccination
from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.medication_status import MedicationStatus
from Domain.value_objects.note_type import NoteType
from Domain.value_objects.record_source import RecordSource
from Domain.value_objects.severity import Severity
from infrastructure.repositories.diagnosis_repository import DiagnosisRepository
from infrastructure.repositories.medication_repository import MedicationRepository
from infrastructure.repositories.clinical_note_repository import ClinicalNoteRepository
from infrastructure.repositories.vaccination_repository import VaccinationRepository
from infrastructure.database.models import ClinicalNoteModel, DiagnosisModel, MedicationModel, VaccinationModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
_PATIENT_ID = uuid.uuid4()
_DOCTOR_ID = uuid.uuid4()


def _make_diagnosis_model(**kwargs) -> Any:
    m = MagicMock(spec=DiagnosisModel)
    m.id = kwargs.get("id", uuid.uuid4())
    m.patient_id = kwargs.get("patient_id", _PATIENT_ID)
    m.doctor_id = kwargs.get("doctor_id", _DOCTOR_ID)
    m.appointment_id = kwargs.get("appointment_id", None)
    m.icd10_code = kwargs.get("icd10_code", None)
    m.diagnosis_name = kwargs.get("diagnosis_name", "Hypertension")
    m.diagnosis_detail = kwargs.get("diagnosis_detail", None)
    m.severity = kwargs.get("severity", None)
    m.status = kwargs.get("status", DiagnosisStatus.ACTIVE)
    m.diagnosed_at = kwargs.get("diagnosed_at", date(2025, 1, 10))
    m.resolved_at = kwargs.get("resolved_at", None)
    m.source = kwargs.get("source", RecordSource.DOCTOR)
    m.created_at = kwargs.get("created_at", _NOW)
    return m


def _make_medication_model(**kwargs) -> Any:
    m = MagicMock(spec=MedicationModel)
    m.id = kwargs.get("id", uuid.uuid4())
    m.patient_id = kwargs.get("patient_id", _PATIENT_ID)
    m.doctor_id = kwargs.get("doctor_id", _DOCTOR_ID)
    m.appointment_id = kwargs.get("appointment_id", None)
    m.drug_name = kwargs.get("drug_name", "Metformin")
    m.dosage = kwargs.get("dosage", "500mg")
    m.frequency = kwargs.get("frequency", "BID")
    m.route = kwargs.get("route", "oral")
    m.start_date = kwargs.get("start_date", date(2025, 1, 10))
    m.end_date = kwargs.get("end_date", None)
    m.status = kwargs.get("status", MedicationStatus.ACTIVE)
    m.notes = kwargs.get("notes", None)
    m.created_at = kwargs.get("created_at", _NOW)
    return m


def _make_note_model(**kwargs) -> Any:
    m = MagicMock(spec=ClinicalNoteModel)
    m.id = kwargs.get("id", uuid.uuid4())
    m.patient_id = kwargs.get("patient_id", _PATIENT_ID)
    m.doctor_id = kwargs.get("doctor_id", _DOCTOR_ID)
    m.appointment_id = kwargs.get("appointment_id", None)
    m.note_type = kwargs.get("note_type", NoteType.SOAP)
    m.content = kwargs.get("content", "Patient reports chest pain.")
    m.is_ai_generated = kwargs.get("is_ai_generated", False)
    m.created_at = kwargs.get("created_at", _NOW)
    return m


def _make_vaccination_model(**kwargs) -> Any:
    m = MagicMock(spec=VaccinationModel)
    m.id = kwargs.get("id", uuid.uuid4())
    m.patient_id = kwargs.get("patient_id", _PATIENT_ID)
    m.vaccine_name = kwargs.get("vaccine_name", "COVID-19")
    m.date_administered = kwargs.get("date_administered", date(2025, 1, 10))
    m.next_due_date = kwargs.get("next_due_date", None)
    m.created_at = kwargs.get("created_at", _NOW)
    return m


def _async_result(scalar_value):
    """Return a mock execute() result whose .scalar_one_or_none() returns scalar_value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = scalar_value if isinstance(scalar_value, list) else []
    result.scalars.return_value = scalars_mock
    return result


def _make_session(execute_return=None):
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_return or _async_result(None))
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# DiagnosisRepository
# ---------------------------------------------------------------------------


class TestDiagnosisRepository:
    async def test_get_by_id_returns_entity(self):
        model = _make_diagnosis_model()
        session = _make_session(_async_result(model))
        repo = DiagnosisRepository(session)

        result = await repo.get_by_id(model.id)

        assert result is not None
        assert result.id == model.id
        assert result.diagnosis_name == model.diagnosis_name

    async def test_get_by_id_returns_none_when_missing(self):
        session = _make_session(_async_result(None))
        repo = DiagnosisRepository(session)

        result = await repo.get_by_id(uuid.uuid4())

        assert result is None

    async def test_save_inserts_new_diagnosis(self):
        # execute returns None (not found) → triggers insert path
        session = _make_session(_async_result(None))
        repo = DiagnosisRepository(session)
        diagnosis = Diagnosis(
            id=uuid.uuid4(),
            patient_id=_PATIENT_ID,
            doctor_id=_DOCTOR_ID,
            diagnosis_name="Diabetes",
            diagnosed_at=date(2025, 1, 10),
        )

        # After refresh, session.refresh will have called with the model;
        # mock _to_entity by patching the model returned after refresh
        session.refresh.side_effect = lambda m: setattr(m, "id", diagnosis.id)

        # Patch the select result to None first (insert), then model after refresh
        await repo.save(diagnosis)
        # add() was called
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_save_updates_existing_diagnosis(self):
        model = _make_diagnosis_model()
        session = _make_session(_async_result(model))
        repo = DiagnosisRepository(session)

        diagnosis = Diagnosis(
            id=model.id,
            patient_id=model.patient_id,
            doctor_id=model.doctor_id,
            diagnosis_name=model.diagnosis_name,
            diagnosed_at=model.diagnosed_at,
            status=DiagnosisStatus.RESOLVED,
        )

        await repo.save(diagnosis)

        # update path: add() should NOT be called
        session.add.assert_not_called()
        session.flush.assert_awaited_once()
        assert model.status == DiagnosisStatus.RESOLVED

    async def test_list_by_patient_returns_entities(self):
        models = [_make_diagnosis_model(patient_id=_PATIENT_ID) for _ in range(3)]
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = models
        result_mock.scalars.return_value = scalars_mock
        session = _make_session(result_mock)
        repo = DiagnosisRepository(session)

        results = await repo.list_by_patient(_PATIENT_ID)

        assert len(results) == 3

    async def test_list_by_patient_with_status_filter(self):
        """Ensure the query runs without error when status filter is provided."""
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        session = _make_session(result_mock)
        repo = DiagnosisRepository(session)

        results = await repo.list_by_patient(_PATIENT_ID, status=DiagnosisStatus.ACTIVE)
        assert results == []

    def test_to_entity_maps_all_fields(self):
        model = _make_diagnosis_model(icd10_code="I10", severity=Severity.MILD)
        entity = DiagnosisRepository._to_entity(model)

        assert entity.id == model.id
        assert entity.icd10_code == "I10"
        assert entity.severity == Severity.MILD
        assert entity.source == model.source


# ---------------------------------------------------------------------------
# MedicationRepository
# ---------------------------------------------------------------------------


class TestMedicationRepository:
    async def test_get_by_id_returns_entity(self):
        model = _make_medication_model()
        session = _make_session(_async_result(model))
        repo = MedicationRepository(session)

        result = await repo.get_by_id(model.id)

        assert result is not None
        assert result.id == model.id
        assert result.drug_name == model.drug_name

    async def test_get_by_id_returns_none_when_missing(self):
        session = _make_session(_async_result(None))
        repo = MedicationRepository(session)

        result = await repo.get_by_id(uuid.uuid4())

        assert result is None

    async def test_save_inserts_new_medication(self):
        session = _make_session(_async_result(None))
        repo = MedicationRepository(session)
        medication = Medication(
            id=uuid.uuid4(),
            patient_id=_PATIENT_ID,
            doctor_id=_DOCTOR_ID,
            drug_name="Lisinopril",
            dosage="10mg",
            frequency="QD",
            route="oral",
            start_date=date(2025, 1, 10),
        )

        await repo.save(medication)
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_save_updates_existing_medication(self):
        model = _make_medication_model()
        session = _make_session(_async_result(model))
        repo = MedicationRepository(session)

        medication = Medication(
            id=model.id,
            patient_id=model.patient_id,
            doctor_id=model.doctor_id,
            drug_name=model.drug_name,
            dosage="1000mg",
            frequency=model.frequency,
            route=model.route,
            start_date=model.start_date,
            status=MedicationStatus.STOPPED,
        )

        await repo.save(medication)
        session.add.assert_not_called()
        assert model.dosage == "1000mg"
        assert model.status == MedicationStatus.STOPPED


class TestVaccinationRepository:
    async def test_save_inserts_new_vaccination(self):
        session = _make_session(_async_result(None))
        repo = VaccinationRepository(session)
        vaccination = Vaccination(
            id=uuid.uuid4(),
            patient_id=_PATIENT_ID,
            vaccine_name="Influenza",
            date_administered=date(2025, 1, 10),
        )

        await repo.save(vaccination)
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_list_by_patient_returns_entities(self):
        models = [_make_vaccination_model(patient_id=_PATIENT_ID) for _ in range(2)]
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = models
        result_mock.scalars.return_value = scalars_mock
        session = _make_session(result_mock)
        repo = VaccinationRepository(session)

        results = await repo.list_by_patient(_PATIENT_ID)

        assert len(results) == 2
        assert results[0].vaccine_name == "COVID-19"

    async def test_list_by_patient_returns_entities(self):
        models = [_make_medication_model(patient_id=_PATIENT_ID) for _ in range(2)]
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = models
        result_mock.scalars.return_value = scalars_mock
        session = _make_session(result_mock)
        repo = MedicationRepository(session)

        results = await repo.list_by_patient(_PATIENT_ID)
        assert len(results) == 2

    async def test_list_by_patient_with_status_filter(self):
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        session = _make_session(result_mock)
        repo = MedicationRepository(session)

        results = await repo.list_by_patient(_PATIENT_ID, status=MedicationStatus.ACTIVE)
        assert results == []

    def test_to_entity_maps_all_fields(self):
        model = _make_medication_model(notes="Take with food", end_date=date(2025, 6, 1))
        entity = MedicationRepository._to_entity(model)

        assert entity.notes == "Take with food"
        assert entity.end_date == date(2025, 6, 1)


# ---------------------------------------------------------------------------
# ClinicalNoteRepository
# ---------------------------------------------------------------------------


class TestClinicalNoteRepository:
    async def test_get_by_id_returns_entity(self):
        model = _make_note_model()
        session = _make_session(_async_result(model))
        repo = ClinicalNoteRepository(session)

        result = await repo.get_by_id(model.id)

        assert result is not None
        assert result.id == model.id
        assert result.content == model.content

    async def test_get_by_id_returns_none_when_missing(self):
        session = _make_session(_async_result(None))
        repo = ClinicalNoteRepository(session)

        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_save_always_inserts(self):
        session = _make_session()  # refresh
        repo = ClinicalNoteRepository(session)
        note = ClinicalNote(
            id=uuid.uuid4(),
            patient_id=_PATIENT_ID,
            doctor_id=_DOCTOR_ID,
            note_type=NoteType.SOAP,
            content="Patient reports headache.",
        )

        await repo.save(note)
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_list_by_patient_returns_entities(self):
        models = [_make_note_model(patient_id=_PATIENT_ID) for _ in range(4)]
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = models
        result_mock.scalars.return_value = scalars_mock
        session = _make_session(result_mock)
        repo = ClinicalNoteRepository(session)

        results = await repo.list_by_patient(_PATIENT_ID)
        assert len(results) == 4

    async def test_list_by_patient_with_appointment_filter(self):
        appt_id = uuid.uuid4()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock.scalars.return_value = scalars_mock
        session = _make_session(result_mock)
        repo = ClinicalNoteRepository(session)

        results = await repo.list_by_patient(_PATIENT_ID, appointment_id=appt_id)
        assert results == []

    def test_to_entity_maps_all_fields(self):
        appt_id = uuid.uuid4()
        model = _make_note_model(appointment_id=appt_id, is_ai_generated=True)
        entity = ClinicalNoteRepository._to_entity(model)

        assert entity.appointment_id == appt_id
        assert entity.is_ai_generated is True
