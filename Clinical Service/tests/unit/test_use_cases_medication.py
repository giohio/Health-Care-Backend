"""Unit tests for medication use cases: PrescribeMedication, ListMedications, UpdateMedicationStatus."""
import uuid
from datetime import date

import pytest

from Application.dtos import CreateMedicationRequest, UpdateMedicationStatusRequest
from Application.exceptions import MedicationNotFoundError
from Application.use_cases.list_medications import ListMedicationsUseCase
from Application.use_cases.prescribe_medication import PrescribeMedicationUseCase
from Application.use_cases.update_medication_status import UpdateMedicationStatusUseCase
from Domain.value_objects.medication_status import MedicationStatus
from tests.conftest import FakeMedicationRepo, make_medication


# ---------------------------------------------------------------------------
# PrescribeMedicationUseCase
# ---------------------------------------------------------------------------


class TestPrescribeMedication:
    @pytest.fixture
    def repo(self) -> FakeMedicationRepo:
        return FakeMedicationRepo()

    @pytest.fixture
    def use_case(self, repo: FakeMedicationRepo) -> PrescribeMedicationUseCase:
        return PrescribeMedicationUseCase(medication_repo=repo)

    async def test_prescribes_and_saves(self, use_case, repo):
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()
        request = CreateMedicationRequest(
            patient_id=patient_id,
            doctor_id=doctor_id,
            drug_name="Metformin",
            start_date=date(2025, 1, 15),
            dosage="500mg",
            frequency="twice daily",
        )

        response = await use_case.execute(request)

        assert response.drug_name == "Metformin"
        assert response.patient_id == patient_id
        assert response.status == MedicationStatus.ACTIVE
        assert len(repo._store) == 1

    async def test_each_prescription_has_unique_id(self, use_case):
        request = CreateMedicationRequest(
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            drug_name="Metformin",
            start_date=date(2025, 1, 15),
        )
        r1 = await use_case.execute(request)
        r2 = await use_case.execute(request)
        assert r1.id != r2.id

    async def test_optional_fields_preserved(self, use_case):
        appt_id = uuid.uuid4()
        request = CreateMedicationRequest(
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            drug_name="Amoxicillin",
            start_date=date(2025, 1, 15),
            end_date=date(2025, 1, 22),
            appointment_id=appt_id,
            route="oral",
            notes="Take with food",
        )
        response = await use_case.execute(request)
        assert response.end_date == date(2025, 1, 22)
        assert response.appointment_id == appt_id
        assert response.route == "oral"


# ---------------------------------------------------------------------------
# ListMedicationsUseCase
# ---------------------------------------------------------------------------


class TestListMedications:
    @pytest.fixture
    def repo(self) -> FakeMedicationRepo:
        return FakeMedicationRepo()

    @pytest.fixture
    def use_case(self, repo: FakeMedicationRepo) -> ListMedicationsUseCase:
        return ListMedicationsUseCase(medication_repo=repo)

    async def test_lists_medications_for_patient(self, use_case, repo):
        patient_id = uuid.uuid4()
        m1 = make_medication(patient_id=patient_id, start_date=date(2025, 1, 1))
        m2 = make_medication(patient_id=patient_id, start_date=date(2025, 2, 1))
        other = make_medication(patient_id=uuid.uuid4(), start_date=date(2025, 1, 1))
        for m in (m1, m2, other):
            await repo.save(m)

        results = await use_case.execute(patient_id=patient_id)
        assert len(results) == 2

    async def test_status_filter(self, use_case, repo):
        patient_id = uuid.uuid4()
        active = make_medication(patient_id=patient_id, status=MedicationStatus.ACTIVE, start_date=date(2025, 1, 1))
        stopped = make_medication(patient_id=patient_id, status=MedicationStatus.STOPPED, start_date=date(2025, 1, 1))
        await repo.save(active)
        await repo.save(stopped)

        results = await use_case.execute(patient_id=patient_id, status=MedicationStatus.ACTIVE)
        assert len(results) == 1
        assert results[0].status == MedicationStatus.ACTIVE

    async def test_no_filter_returns_all_statuses(self, use_case, repo):
        patient_id = uuid.uuid4()
        for status in MedicationStatus:
            await repo.save(make_medication(patient_id=patient_id, status=status, start_date=date(2025, 1, 1)))

        results = await use_case.execute(patient_id=patient_id)
        assert len(results) == len(list(MedicationStatus))

    async def test_empty_patient_returns_empty(self, use_case):
        results = await use_case.execute(patient_id=uuid.uuid4())
        assert results == []


# ---------------------------------------------------------------------------
# UpdateMedicationStatusUseCase
# ---------------------------------------------------------------------------


class TestUpdateMedicationStatus:
    @pytest.fixture
    def repo(self) -> FakeMedicationRepo:
        return FakeMedicationRepo()

    @pytest.fixture
    def use_case(self, repo: FakeMedicationRepo) -> UpdateMedicationStatusUseCase:
        return UpdateMedicationStatusUseCase(medication_repo=repo)

    async def test_stop_medication(self, use_case, repo):
        medication = make_medication(status=MedicationStatus.ACTIVE, start_date=date(2025, 1, 1))
        await repo.save(medication)

        response = await use_case.execute(
            medication_id=medication.id,
            request=UpdateMedicationStatusRequest(status=MedicationStatus.STOPPED),
        )
        assert response.status == MedicationStatus.STOPPED

    async def test_complete_medication(self, use_case, repo):
        medication = make_medication(status=MedicationStatus.ACTIVE, start_date=date(2025, 1, 1))
        await repo.save(medication)

        response = await use_case.execute(
            medication_id=medication.id,
            request=UpdateMedicationStatusRequest(status=MedicationStatus.COMPLETED),
        )
        assert response.status == MedicationStatus.COMPLETED

    async def test_end_date_set(self, use_case, repo):
        medication = make_medication(status=MedicationStatus.ACTIVE, start_date=date(2025, 1, 1))
        await repo.save(medication)

        end_date = date(2025, 3, 1)
        response = await use_case.execute(
            medication_id=medication.id,
            request=UpdateMedicationStatusRequest(
                status=MedicationStatus.STOPPED, end_date=end_date
            ),
        )
        assert response.end_date == end_date

    async def test_not_found_raises_error(self, use_case):
        with pytest.raises(MedicationNotFoundError):
            await use_case.execute(
                medication_id=uuid.uuid4(),
                request=UpdateMedicationStatusRequest(status=MedicationStatus.STOPPED),
            )

    async def test_stop_saves_to_repo(self, use_case, repo):
        medication = make_medication(status=MedicationStatus.ACTIVE, start_date=date(2025, 1, 1))
        await repo.save(medication)

        await use_case.execute(
            medication_id=medication.id,
            request=UpdateMedicationStatusRequest(status=MedicationStatus.STOPPED),
        )
        # Confirm persistence
        stored = repo._store[medication.id]
        assert stored.status == MedicationStatus.STOPPED
