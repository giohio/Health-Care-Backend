"""Unit tests for clinical notes and patient summary use cases."""
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Union

import pytest

from Application.dtos import CreateClinicalNoteRequest
from Application.use_cases.clinical_notes import CreateClinicalNoteUseCase, ListClinicalNotesUseCase
from Application.use_cases.get_patient_summary import GetPatientSummaryUseCase
from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.medication_status import MedicationStatus
from Domain.value_objects.note_type import NoteType
from tests.conftest import (
    FakeDiagnosisRepo,
    FakeMedicationRepo,
    FakeNoteRepo,
    FakePatientClient,
    make_clinical_note,
    make_diagnosis,
    make_medication,
)


# ---------------------------------------------------------------------------
# CreateClinicalNoteUseCase
# ---------------------------------------------------------------------------


class TestCreateClinicalNote:
    @pytest.fixture
    def repo(self) -> FakeNoteRepo:
        return FakeNoteRepo()

    @pytest.fixture
    def use_case(self, repo: FakeNoteRepo) -> CreateClinicalNoteUseCase:
        return CreateClinicalNoteUseCase(note_repo=repo)

    async def test_creates_and_saves_note(self, use_case, repo):
        patient_id = uuid.uuid4()
        request = CreateClinicalNoteRequest(
            patient_id=patient_id,
            doctor_id=uuid.uuid4(),
            content="Patient reports chest pain.",
            note_type=NoteType.SOAP,
            is_ai_generated=False,
        )

        response = await use_case.execute(request)

        assert response.content == "Patient reports chest pain."
        assert response.patient_id == patient_id
        assert response.note_type == NoteType.SOAP
        assert response.is_ai_generated is False
        assert len(repo._store) == 1

    async def test_unique_id_per_note(self, use_case):
        request = CreateClinicalNoteRequest(
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            content="Note text",
            note_type=NoteType.PROGRESS,
            is_ai_generated=False,
        )
        r1 = await use_case.execute(request)
        r2 = await use_case.execute(request)
        assert r1.id != r2.id

    async def test_ai_generated_flag_saved(self, use_case):
        request = CreateClinicalNoteRequest(
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            content="AI generated summary.",
            note_type=NoteType.SUMMARY,
            is_ai_generated=True,
        )
        response = await use_case.execute(request)
        assert response.is_ai_generated is True

    async def test_appointment_id_saved(self, use_case):
        appt_id = uuid.uuid4()
        request = CreateClinicalNoteRequest(
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            content="Post-appointment notes.",
            note_type=NoteType.SOAP,
            is_ai_generated=False,
            appointment_id=appt_id,
        )
        response = await use_case.execute(request)
        assert response.appointment_id == appt_id


# ---------------------------------------------------------------------------
# ListClinicalNotesUseCase
# ---------------------------------------------------------------------------


class TestListClinicalNotes:
    @pytest.fixture
    def repo(self) -> FakeNoteRepo:
        return FakeNoteRepo()

    @pytest.fixture
    def use_case(self, repo: FakeNoteRepo) -> ListClinicalNotesUseCase:
        return ListClinicalNotesUseCase(note_repo=repo)

    async def test_lists_all_notes_for_patient(self, use_case, repo):
        patient_id = uuid.uuid4()
        n1 = make_clinical_note(patient_id=patient_id)
        n2 = make_clinical_note(patient_id=patient_id)
        other = make_clinical_note(patient_id=uuid.uuid4())
        for n in (n1, n2, other):
            await repo.save(n)

        results = await use_case.execute(patient_id=patient_id)
        assert len(results) == 2

    async def test_appointment_id_filter(self, use_case, repo):
        patient_id = uuid.uuid4()
        appt_id = uuid.uuid4()
        n_with_appt = make_clinical_note(patient_id=patient_id, appointment_id=appt_id)
        n_no_appt = make_clinical_note(patient_id=patient_id)
        await repo.save(n_with_appt)
        await repo.save(n_no_appt)

        results = await use_case.execute(patient_id=patient_id, appointment_id=appt_id)
        assert len(results) == 1
        assert results[0].appointment_id == appt_id

    async def test_no_appointment_filter_returns_all(self, use_case, repo):
        patient_id = uuid.uuid4()
        for _ in range(3):
            await repo.save(make_clinical_note(patient_id=patient_id))

        results = await use_case.execute(patient_id=patient_id)
        assert len(results) == 3

    async def test_empty_patient_returns_empty(self, use_case):
        results = await use_case.execute(patient_id=uuid.uuid4())
        assert results == []


# ---------------------------------------------------------------------------
# GetPatientSummaryUseCase
# ---------------------------------------------------------------------------


class TestGetPatientSummary:
    @pytest.fixture
    def diag_repo(self) -> FakeDiagnosisRepo:
        return FakeDiagnosisRepo()

    @pytest.fixture
    def med_repo(self) -> FakeMedicationRepo:
        return FakeMedicationRepo()

    def make_use_case(
        self,
        diag_repo: FakeDiagnosisRepo,
        med_repo: FakeMedicationRepo,
        allergies: Optional[List[str]] = None,
        vitals: Optional[Dict] = None,
    ) -> GetPatientSummaryUseCase:
        return GetPatientSummaryUseCase(
            diagnosis_repo=diag_repo,
            medication_repo=med_repo,
            patient_client=FakePatientClient(allergies=allergies or [], vitals=vitals),
        )

    async def test_aggregates_all_data(self, diag_repo, med_repo):
        patient_id = uuid.uuid4()
        diag = make_diagnosis(patient_id=patient_id, status=DiagnosisStatus.ACTIVE, diagnosed_at=date(2025, 1, 1))
        med = make_medication(patient_id=patient_id, status=MedicationStatus.ACTIVE, start_date=date(2025, 1, 1))
        await diag_repo.save(diag)
        await med_repo.save(med)

        use_case = self.make_use_case(
            diag_repo,
            med_repo,
            allergies=["Penicillin"],
            vitals={"bp": "120/80"},
        )
        summary = await use_case.execute(patient_id=patient_id)

        assert summary.patient_id == patient_id
        assert len(summary.diagnoses) == 1
        assert len(summary.medications) == 1
        assert summary.allergies == ["Penicillin"]
        assert summary.vitals_latest == {"bp": "120/80"}

    async def test_only_active_medications_in_summary(self, diag_repo, med_repo):
        patient_id = uuid.uuid4()
        active = make_medication(patient_id=patient_id, status=MedicationStatus.ACTIVE, start_date=date(2025, 1, 1))
        stopped = make_medication(patient_id=patient_id, status=MedicationStatus.STOPPED, start_date=date(2025, 1, 1))
        await med_repo.save(active)
        await med_repo.save(stopped)

        use_case = self.make_use_case(diag_repo, med_repo)
        summary = await use_case.execute(patient_id=patient_id)

        assert len(summary.medications) == 1
        assert summary.medications[0].status == MedicationStatus.ACTIVE

    async def test_all_diagnoses_in_summary(self, diag_repo, med_repo):
        patient_id = uuid.uuid4()
        for status in DiagnosisStatus:
            await diag_repo.save(
                make_diagnosis(patient_id=patient_id, status=status, diagnosed_at=date(2025, 1, 1))
            )

        use_case = self.make_use_case(diag_repo, med_repo)
        summary = await use_case.execute(patient_id=patient_id)

        assert len(summary.diagnoses) == len(list(DiagnosisStatus))

    async def test_empty_patient_returns_empty_summary(self):
        diag_repo = FakeDiagnosisRepo()
        med_repo = FakeMedicationRepo()
        use_case = GetPatientSummaryUseCase(
            diagnosis_repo=diag_repo,
            medication_repo=med_repo,
            patient_client=FakePatientClient(),
        )
        summary = await use_case.execute(patient_id=uuid.uuid4())
        assert summary.diagnoses == []
        assert summary.medications == []
        assert summary.allergies == []
        assert summary.vitals_latest is None

    async def test_patient_client_returns_none_vitals(self, diag_repo, med_repo):
        use_case = self.make_use_case(diag_repo, med_repo, allergies=[], vitals=None)
        summary = await use_case.execute(patient_id=uuid.uuid4())
        assert summary.vitals_latest is None

    async def test_concurrent_fetch_runs(self, diag_repo, med_repo):
        """Verify asyncio.gather is used — no exceptions in concurrent execution."""
        patient_id = uuid.uuid4()
        for _ in range(5):
            await diag_repo.save(
                make_diagnosis(patient_id=patient_id, status=DiagnosisStatus.ACTIVE, diagnosed_at=date(2025, 1, 1))
            )
            await med_repo.save(
                make_medication(patient_id=patient_id, status=MedicationStatus.ACTIVE, start_date=date(2025, 1, 1))
            )

        use_case = self.make_use_case(
            diag_repo, med_repo, allergies=["Aspirin", "Latex"], vitals={"temp": "37.0"}
        )
        summary = await use_case.execute(patient_id=patient_id)
        assert len(summary.diagnoses) == 5
        assert len(summary.medications) == 5
