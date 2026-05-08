"""Route-level integration tests for Clinical Service using FastAPI TestClient."""
import asyncio
import uuid
from datetime import date
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from Application.dtos import (
    ClinicalNoteResponse,
    DiagnosisResponse,
    MedicationResponse,
    PatientSummaryResponse,
    VaccinationResponse,
)
from Application.exceptions import DiagnosisNotFoundError, MedicationNotFoundError
from Application.use_cases.add_diagnosis import AddDiagnosisUseCase
from Application.use_cases.clinical_notes import CreateClinicalNoteUseCase, ListClinicalNotesUseCase
from Application.use_cases.get_patient_summary import GetPatientSummaryUseCase
from Application.use_cases.list_diagnoses import ListDiagnosesUseCase
from Application.use_cases.list_medications import ListMedicationsUseCase
from Application.use_cases.list_vaccinations import ListVaccinationsUseCase
from Application.use_cases.prescribe_medication import PrescribeMedicationUseCase
from Application.use_cases.update_diagnosis import UpdateDiagnosisUseCase
from Application.use_cases.update_medication_status import UpdateMedicationStatusUseCase
from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.medication_status import MedicationStatus
from Domain.value_objects.note_type import NoteType
from Domain.value_objects.record_source import RecordSource
from fastapi import FastAPI
from presentation.dependencies import (
    get_add_diagnosis_use_case,
    get_create_note_use_case,
    get_list_diagnoses_use_case,
    get_list_medications_use_case,
    get_list_notes_use_case,
    get_list_vaccinations_use_case,
    get_patient_summary_use_case,
    get_prescribe_medication_use_case,
    get_update_diagnosis_use_case,
    get_update_medication_status_use_case,
)
from presentation.routes.clinical import router

app = FastAPI()
app.include_router(router, prefix="/clinical")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "clinical-service"}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

DOCTOR_ID = uuid.uuid4()
PATIENT_ID = uuid.uuid4()
DIAGNOSIS_ID = uuid.uuid4()
MEDICATION_ID = uuid.uuid4()
NOTE_ID = uuid.uuid4()
VACCINATION_ID = uuid.uuid4()

DOCTOR_HEADERS = {
    "x-user-id": str(DOCTOR_ID),
    "x-user-role": "doctor",
}

PATIENT_HEADERS = {
    "x-user-id": str(PATIENT_ID),
    "x-user-role": "patient",
}


def make_diagnosis_response(**kwargs) -> DiagnosisResponse:
    defaults = {
        "id": DIAGNOSIS_ID,
        "patient_id": PATIENT_ID,
        "doctor_id": DOCTOR_ID,
        "appointment_id": None,
        "icd10_code": None,
        "diagnosis_name": "Hypertension",
        "diagnosis_detail": None,
        "severity": None,
        "status": DiagnosisStatus.ACTIVE,
        "diagnosed_at": date(2025, 1, 15),
        "resolved_at": None,
        "source": RecordSource.DOCTOR,
        "created_at": None,
    }
    defaults.update(kwargs)
    return DiagnosisResponse(**defaults)


def make_medication_response(**kwargs) -> MedicationResponse:
    defaults = {
        "id": MEDICATION_ID,
        "patient_id": PATIENT_ID,
        "doctor_id": DOCTOR_ID,
        "appointment_id": None,
        "drug_name": "Metformin",
        "dosage": "500mg",
        "frequency": "twice daily",
        "route": None,
        "start_date": date(2025, 1, 15),
        "end_date": None,
        "status": MedicationStatus.ACTIVE,
        "notes": None,
        "created_at": None,
    }
    defaults.update(kwargs)
    return MedicationResponse(**defaults)


def make_note_response(**kwargs) -> ClinicalNoteResponse:
    defaults = {
        "id": NOTE_ID,
        "patient_id": PATIENT_ID,
        "doctor_id": DOCTOR_ID,
        "appointment_id": None,
        "note_type": NoteType.SOAP,
        "content": "Patient stable.",
        "is_ai_generated": False,
        "created_at": None,
    }
    defaults.update(kwargs)
    return ClinicalNoteResponse(**defaults)


def make_summary_response() -> PatientSummaryResponse:
    return PatientSummaryResponse(
        patient_id=PATIENT_ID,
        diagnoses=[make_diagnosis_response()],
        medications=[make_medication_response()],
        allergies=["Penicillin"],
        vitals_latest={"bp": "120/80"},
    )


def make_vaccination_response(**kwargs) -> VaccinationResponse:
    defaults = {
        "id": VACCINATION_ID,
        "patient_id": PATIENT_ID,
        "vaccine_name": "COVID-19",
        "date_administered": date(2025, 1, 15),
        "next_due_date": None,
        "created_at": None,
    }
    defaults.update(kwargs)
    return VaccinationResponse(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """TestClient with all use cases mocked."""
    return TestClient(app, raise_server_exceptions=False)


def override_use_case(dependency_fn, mock_return_value):
    """Helper that returns a DI override callable."""

    async def _use_case_fn(*args, **kwargs):
        await asyncio.sleep(0)
        return mock_return_value

    return _use_case_fn


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_check(self):
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestVaccinationsRoute:
    def test_doctor_can_list_vaccinations(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[make_vaccination_response()])
        app.dependency_overrides[get_list_vaccinations_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/clinical/patients/{PATIENT_ID}/vaccinations",
                    headers=DOCTOR_HEADERS,
                )
            assert resp.status_code == 200
            assert resp.json()[0]["vaccine_name"] == "COVID-19"
        finally:
            app.dependency_overrides.clear()

    def test_patient_denied_other_patient_vaccinations(self):
        other_patient = uuid.uuid4()
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[])
        app.dependency_overrides[get_list_vaccinations_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/clinical/patients/{other_patient}/vaccinations",
                    headers=PATIENT_HEADERS,
                )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_empty_vaccination_list_returns_200(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[])
        app.dependency_overrides[get_list_vaccinations_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/clinical/patients/{PATIENT_ID}/vaccinations",
                    headers=DOCTOR_HEADERS,
                )
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Diagnoses
# ---------------------------------------------------------------------------


class TestListDiagnosesRoute:
    def test_doctor_can_list_diagnoses(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[make_diagnosis_response()])
        app.dependency_overrides[get_list_diagnoses_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/clinical/patients/{PATIENT_ID}/diagnoses",
                    headers=DOCTOR_HEADERS,
                )
            assert resp.status_code == 200
            assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()

    def test_patient_can_list_own_diagnoses(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[])
        app.dependency_overrides[get_list_diagnoses_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/clinical/patients/{PATIENT_ID}/diagnoses",
                    headers=PATIENT_HEADERS,
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_patient_denied_other_patient_diagnoses(self):
        other_patient = uuid.uuid4()
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[])
        app.dependency_overrides[get_list_diagnoses_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/clinical/patients/{other_patient}/diagnoses",
                    headers=PATIENT_HEADERS,
                )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_missing_headers_returns_401(self):
        with TestClient(app) as client:
            resp = client.get(f"/clinical/patients/{PATIENT_ID}/diagnoses")
        assert resp.status_code == 401


class TestAddDiagnosisRoute:
    def test_doctor_adds_diagnosis(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=make_diagnosis_response())
        app.dependency_overrides[get_add_diagnosis_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.post(
                    f"/clinical/patients/{PATIENT_ID}/diagnoses",
                    headers=DOCTOR_HEADERS,
                    json={
                        "patient_id": str(PATIENT_ID),
                        "doctor_id": str(DOCTOR_ID),
                        "diagnosis_name": "Hypertension",
                        "diagnosed_at": "2025-01-15",
                    },
                )
            assert resp.status_code == 201
        finally:
            app.dependency_overrides.clear()

    def test_patient_cannot_add_diagnosis(self):
        with TestClient(app) as client:
            resp = client.post(
                f"/clinical/patients/{PATIENT_ID}/diagnoses",
                headers=PATIENT_HEADERS,
                json={
                    "patient_id": str(PATIENT_ID),
                    "doctor_id": str(DOCTOR_ID),
                    "diagnosis_name": "Hypertension",
                    "diagnosed_at": "2025-01-15",
                },
            )
        assert resp.status_code == 403


class TestUpdateDiagnosisRoute:
    def test_doctor_can_update_diagnosis(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=make_diagnosis_response(status=DiagnosisStatus.RESOLVED)
        )
        app.dependency_overrides[get_update_diagnosis_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.patch(
                    f"/clinical/patients/{PATIENT_ID}/diagnoses/{DIAGNOSIS_ID}",
                    headers=DOCTOR_HEADERS,
                    json={"status": "resolved"},
                )
            assert resp.status_code == 200
            assert resp.json()["status"] == "resolved"
        finally:
            app.dependency_overrides.clear()

    def test_update_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=DiagnosisNotFoundError())
        app.dependency_overrides[get_update_diagnosis_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.patch(
                    f"/clinical/patients/{PATIENT_ID}/diagnoses/{DIAGNOSIS_ID}",
                    headers=DOCTOR_HEADERS,
                    json={"status": "resolved"},
                )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------


class TestPrescribeMedicationRoute:
    def test_doctor_prescribes_medication(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=make_medication_response())
        app.dependency_overrides[get_prescribe_medication_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.post(
                    f"/clinical/patients/{PATIENT_ID}/medications",
                    headers=DOCTOR_HEADERS,
                    json={
                        "patient_id": str(PATIENT_ID),
                        "doctor_id": str(DOCTOR_ID),
                        "drug_name": "Metformin",
                        "start_date": "2025-01-15",
                    },
                )
            assert resp.status_code == 201
        finally:
            app.dependency_overrides.clear()

    def test_patient_cannot_prescribe(self):
        with TestClient(app) as client:
            resp = client.post(
                f"/clinical/patients/{PATIENT_ID}/medications",
                headers=PATIENT_HEADERS,
                json={
                    "patient_id": str(PATIENT_ID),
                    "doctor_id": str(DOCTOR_ID),
                    "drug_name": "Metformin",
                    "start_date": "2025-01-15",
                },
            )
        assert resp.status_code == 403


class TestUpdateMedicationStatusRoute:
    def test_doctor_stops_medication(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=make_medication_response(status=MedicationStatus.STOPPED)
        )
        app.dependency_overrides[get_update_medication_status_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.patch(
                    f"/clinical/medications/{MEDICATION_ID}",
                    headers=DOCTOR_HEADERS,
                    json={"status": "stopped"},
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_medication_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=MedicationNotFoundError())
        app.dependency_overrides[get_update_medication_status_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.patch(
                    f"/clinical/medications/{MEDICATION_ID}",
                    headers=DOCTOR_HEADERS,
                    json={"status": "stopped"},
                )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Clinical notes
# ---------------------------------------------------------------------------


class TestCreateNoteRoute:
    def test_doctor_creates_note(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=make_note_response())
        app.dependency_overrides[get_create_note_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.post(
                    f"/clinical/patients/{PATIENT_ID}/notes",
                    headers=DOCTOR_HEADERS,
                    json={
                        "patient_id": str(PATIENT_ID),
                        "doctor_id": str(DOCTOR_ID),
                        "content": "Patient stable.",
                        "note_type": "soap",
                        "is_ai_generated": False,
                    },
                )
            assert resp.status_code == 201
        finally:
            app.dependency_overrides.clear()

    def test_patient_cannot_create_note(self):
        with TestClient(app) as client:
            resp = client.post(
                f"/clinical/patients/{PATIENT_ID}/notes",
                headers=PATIENT_HEADERS,
                json={
                    "patient_id": str(PATIENT_ID),
                    "doctor_id": str(DOCTOR_ID),
                    "content": "Patient stable.",
                    "note_type": "soap",
                    "is_ai_generated": False,
                },
            )
        assert resp.status_code == 403


class TestListNotesRoute:
    def test_doctor_lists_notes(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[make_note_response()])
        app.dependency_overrides[get_list_notes_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/clinical/patients/{PATIENT_ID}/notes",
                    headers=DOCTOR_HEADERS,
                )
            assert resp.status_code == 200
            assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()

    def test_patient_denied_other_patients_notes(self):
        other_patient = uuid.uuid4()
        with TestClient(app) as client:
            resp = client.get(
                f"/clinical/patients/{other_patient}/notes",
                headers=PATIENT_HEADERS,
            )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Summary route
# ---------------------------------------------------------------------------


class TestSummaryRoute:
    def test_doctor_fetches_summary(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=make_summary_response())
        app.dependency_overrides[get_patient_summary_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/clinical/patients/{PATIENT_ID}/summary",
                    headers=DOCTOR_HEADERS,
                )
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["diagnoses"]) == 1
            assert body["allergies"] == ["Penicillin"]
        finally:
            app.dependency_overrides.clear()

    def test_patient_can_fetch_own_summary(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=make_summary_response())
        app.dependency_overrides[get_patient_summary_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/clinical/patients/{PATIENT_ID}/summary",
                    headers=PATIENT_HEADERS,
                )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_patient_denied_other_patients_summary(self):
        other_patient = uuid.uuid4()
        with TestClient(app) as client:
            resp = client.get(
                f"/clinical/patients/{other_patient}/summary",
                headers=PATIENT_HEADERS,
            )
        assert resp.status_code == 403
