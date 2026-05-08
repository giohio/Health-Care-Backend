"""Unit tests for diagnosis use cases: AddDiagnosis, ListDiagnoses, UpdateDiagnosis."""
import uuid
from datetime import date, datetime, timezone

import pytest

from Application.dtos import CreateDiagnosisRequest, UpdateDiagnosisRequest
from Application.exceptions import DiagnosisNotFoundError
from Application.use_cases.add_diagnosis import AddDiagnosisUseCase
from Application.use_cases.list_diagnoses import ListDiagnosesUseCase
from Application.use_cases.update_diagnosis import UpdateDiagnosisUseCase
from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.record_source import RecordSource
from Domain.value_objects.severity import Severity
from tests.conftest import FakeDiagnosisRepo, make_diagnosis


# ---------------------------------------------------------------------------
# AddDiagnosisUseCase
# ---------------------------------------------------------------------------


class TestAddDiagnosis:
    @pytest.fixture
    def repo(self) -> FakeDiagnosisRepo:
        return FakeDiagnosisRepo()

    @pytest.fixture
    def use_case(self, repo: FakeDiagnosisRepo) -> AddDiagnosisUseCase:
        return AddDiagnosisUseCase(diagnosis_repo=repo)

    async def test_creates_diagnosis_and_saves(self, use_case, repo):
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()
        request = CreateDiagnosisRequest(
            patient_id=patient_id,
            doctor_id=doctor_id,
            diagnosis_name="Hypertension",
            diagnosed_at=date(2025, 1, 10),
        )

        response = await use_case.execute(request)

        assert response.diagnosis_name == "Hypertension"
        assert response.patient_id == patient_id
        assert response.doctor_id == doctor_id
        assert response.status == DiagnosisStatus.ACTIVE
        assert response.source == RecordSource.DOCTOR
        # Persisted in repo
        assert len(repo._store) == 1

    async def test_created_id_is_unique(self, use_case):
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()
        request = CreateDiagnosisRequest(
            patient_id=patient_id,
            doctor_id=doctor_id,
            diagnosis_name="Diabetes",
            diagnosed_at=date(2025, 1, 10),
        )
        r1 = await use_case.execute(request)
        r2 = await use_case.execute(request)
        assert r1.id != r2.id

    async def test_optional_fields_are_preserved(self, use_case, repo):
        appt_id = uuid.uuid4()
        request = CreateDiagnosisRequest(
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            diagnosis_name="Hypertension",
            diagnosed_at=date(2025, 1, 10),
            appointment_id=appt_id,
            icd10_code="I10",
            severity=Severity.MODERATE,
        )
        response = await use_case.execute(request)

        assert response.appointment_id == appt_id
        assert response.icd10_code == "I10"
        assert response.severity == Severity.MODERATE


# ---------------------------------------------------------------------------
# ListDiagnosesUseCase
# ---------------------------------------------------------------------------


class TestListDiagnoses:
    @pytest.fixture
    def repo(self) -> FakeDiagnosisRepo:
        return FakeDiagnosisRepo()

    @pytest.fixture
    def use_case(self, repo: FakeDiagnosisRepo) -> ListDiagnosesUseCase:
        return ListDiagnosesUseCase(diagnosis_repo=repo)

    async def test_returns_diagnoses_for_patient(self, use_case, repo):
        patient_id = uuid.uuid4()
        d1 = make_diagnosis(patient_id=patient_id, diagnosed_at=date(2025, 1, 1))
        d2 = make_diagnosis(patient_id=patient_id, diagnosed_at=date(2025, 2, 1))
        other_patient = make_diagnosis(patient_id=uuid.uuid4())
        for d in (d1, d2, other_patient):
            await repo.save(d)

        responses = await use_case.execute(patient_id=patient_id)
        assert len(responses) == 2

    async def test_status_filter_applied(self, use_case, repo):
        patient_id = uuid.uuid4()
        active = make_diagnosis(patient_id=patient_id, status=DiagnosisStatus.ACTIVE, diagnosed_at=date(2025, 1, 1))
        resolved = make_diagnosis(patient_id=patient_id, status=DiagnosisStatus.RESOLVED, diagnosed_at=date(2025, 1, 1))
        await repo.save(active)
        await repo.save(resolved)

        active_results = await use_case.execute(patient_id=patient_id, status=DiagnosisStatus.ACTIVE)
        assert len(active_results) == 1
        assert active_results[0].status == DiagnosisStatus.ACTIVE

    async def test_no_filter_returns_all(self, use_case, repo):
        patient_id = uuid.uuid4()
        for status in DiagnosisStatus:
            await repo.save(make_diagnosis(patient_id=patient_id, status=status, diagnosed_at=date(2025, 1, 1)))

        results = await use_case.execute(patient_id=patient_id)
        assert len(results) == len(list(DiagnosisStatus))

    async def test_empty_patient_returns_empty(self, use_case):
        results = await use_case.execute(patient_id=uuid.uuid4())
        assert results == []


# ---------------------------------------------------------------------------
# UpdateDiagnosisUseCase
# ---------------------------------------------------------------------------


class TestUpdateDiagnosis:
    @pytest.fixture
    def repo(self) -> FakeDiagnosisRepo:
        return FakeDiagnosisRepo()

    @pytest.fixture
    def use_case(self, repo: FakeDiagnosisRepo) -> UpdateDiagnosisUseCase:
        return UpdateDiagnosisUseCase(diagnosis_repo=repo)

    async def test_partial_update_status(self, use_case, repo):
        diagnosis = make_diagnosis(status=DiagnosisStatus.ACTIVE)
        await repo.save(diagnosis)

        response = await use_case.execute(
            diagnosis_id=diagnosis.id,
            request=UpdateDiagnosisRequest(status=DiagnosisStatus.RESOLVED),
        )

        assert response.status == DiagnosisStatus.RESOLVED
        # Name unchanged
        assert response.diagnosis_name == diagnosis.diagnosis_name

    async def test_partial_update_severity(self, use_case, repo):
        diagnosis = make_diagnosis(severity=Severity.MILD)
        await repo.save(diagnosis)

        response = await use_case.execute(
            diagnosis_id=diagnosis.id,
            request=UpdateDiagnosisRequest(severity=Severity.SEVERE),
        )
        assert response.severity == Severity.SEVERE

    async def test_update_icd10_code(self, use_case, repo):
        diagnosis = make_diagnosis(icd10_code=None)
        await repo.save(diagnosis)

        response = await use_case.execute(
            diagnosis_id=diagnosis.id,
            request=UpdateDiagnosisRequest(icd10_code="I10"),
        )
        assert response.icd10_code == "I10"

    async def test_not_found_raises_error(self, use_case):
        with pytest.raises(DiagnosisNotFoundError):
            await use_case.execute(
                diagnosis_id=uuid.uuid4(),
                request=UpdateDiagnosisRequest(status=DiagnosisStatus.RESOLVED),
            )

    async def test_empty_request_changes_nothing(self, use_case, repo):
        diagnosis = make_diagnosis(status=DiagnosisStatus.ACTIVE, severity=Severity.MILD)
        await repo.save(diagnosis)

        response = await use_case.execute(
            diagnosis_id=diagnosis.id,
            request=UpdateDiagnosisRequest(),
        )
        assert response.status == DiagnosisStatus.ACTIVE
        assert response.severity == Severity.MILD
