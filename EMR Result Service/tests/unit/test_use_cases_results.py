"""Unit tests for EMR use cases: CreateLabOrder, ListLabOrders, UploadLabResult, GetLabResult, ListLabResults."""
import uuid
from datetime import datetime, timezone

import pytest

from Application.dtos import CreateLabOrderRequest, CreateLabResultRequest, UpdateAIDraftRequest
from Application.exceptions import (
    DuplicateLabOrderError,
    LabOrderNotFoundError,
    LabResultNotFoundError,
    ResultNotAccessibleError,
)
from Application.use_cases.create_lab_order import CreateLabOrderUseCase
from Application.use_cases.get_lab_readiness import GetLabReadinessUseCase
from Application.use_cases.get_lab_results import GetLabResultUseCase, ListLabResultsUseCase
from Application.use_cases.list_lab_orders import ListLabOrdersUseCase
from Application.use_cases.update_ai_draft import UpdateAIDraftUseCase
from Application.use_cases.upload_lab_result import UploadLabResultUseCase
from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType
from tests.conftest import FakeLabOrderRepo, FakeLabResultRepo, make_lab_order, make_lab_result

NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# CreateLabOrderUseCase
# ---------------------------------------------------------------------------


class TestCreateLabOrder:
    @pytest.fixture
    def repo(self) -> FakeLabOrderRepo:
        return FakeLabOrderRepo()

    @pytest.fixture
    def use_case(self, repo: FakeLabOrderRepo) -> CreateLabOrderUseCase:
        return CreateLabOrderUseCase(order_repo=repo)

    async def test_creates_lab_order(self, use_case, repo):
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()
        request = CreateLabOrderRequest(
            patient_id=patient_id,
            doctor_id=doctor_id,
            test_name="Complete Blood Count",
        )

        response = await use_case.execute(request)

        assert response.patient_id == patient_id
        assert response.test_name == "Complete Blood Count"
        assert response.priority == OrderPriority.ROUTINE
        assert len(repo._store) == 1

    async def test_each_order_has_unique_id(self, use_case):
        request = CreateLabOrderRequest(
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            test_name="Urinalysis",
        )
        r1 = await use_case.execute(request)
        r2 = await use_case.execute(request)
        assert r1.id != r2.id

    async def test_optional_fields_preserved(self, use_case):
        appt_id = uuid.uuid4()
        request = CreateLabOrderRequest(
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            test_name="ECG",
            appointment_id=appt_id,
            test_type=TestType.ECG,
            department="Cardiology",
            instructions="Fast for 4 hours",
            priority=OrderPriority.URGENT,
        )
        response = await use_case.execute(request)
        assert response.appointment_id == appt_id
        assert response.test_type == TestType.ECG
        assert response.department == "Cardiology"
        assert response.priority == OrderPriority.URGENT

    async def test_rejects_duplicate_test_name_in_same_appointment(self, use_case):
        appt_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()
        request = CreateLabOrderRequest(
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_id=appt_id,
            test_name="Complete Blood Count",
        )

        await use_case.execute(request)

        with pytest.raises(DuplicateLabOrderError):
            await use_case.execute(CreateLabOrderRequest(
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_id=appt_id,
                test_name=" complete   blood count ",
            ))


# ---------------------------------------------------------------------------
# ListLabOrdersUseCase
# ---------------------------------------------------------------------------


class TestListLabOrders:
    @pytest.fixture
    def repo(self) -> FakeLabOrderRepo:
        return FakeLabOrderRepo()

    @pytest.fixture
    def use_case(self, repo: FakeLabOrderRepo) -> ListLabOrdersUseCase:
        return ListLabOrdersUseCase(order_repo=repo)

    async def test_list_by_patient(self, use_case, repo):
        patient_id = uuid.uuid4()
        o1 = make_lab_order(patient_id=patient_id)
        o2 = make_lab_order(patient_id=patient_id)
        other = make_lab_order(patient_id=uuid.uuid4())
        for o in (o1, o2, other):
            await repo.save(o)

        results = await use_case.execute(patient_id=patient_id)
        assert len(results) == 2

    async def test_list_by_doctor(self, use_case, repo):
        doctor_id = uuid.uuid4()
        o = make_lab_order(doctor_id=doctor_id)
        other = make_lab_order(doctor_id=uuid.uuid4())
        await repo.save(o)
        await repo.save(other)

        results = await use_case.execute(doctor_id=doctor_id)
        assert len(results) == 1

    async def test_list_no_filter_returns_all(self, use_case, repo):
        for _ in range(3):
            await repo.save(make_lab_order())

        results = await use_case.execute()
        assert len(results) == 3

    async def test_empty_returns_empty(self, use_case):
        results = await use_case.execute()
        assert results == []


# ---------------------------------------------------------------------------
# UploadLabResultUseCase
# ---------------------------------------------------------------------------


class TestUploadLabResult:
    @pytest.fixture
    def order_repo(self) -> FakeLabOrderRepo:
        return FakeLabOrderRepo()

    @pytest.fixture
    def result_repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    @pytest.fixture
    def use_case(self, order_repo, result_repo) -> UploadLabResultUseCase:
        return UploadLabResultUseCase(order_repo=order_repo, result_repo=result_repo)

    async def test_creates_pending_result(self, use_case, order_repo, result_repo):
        order = make_lab_order()
        await order_repo.save(order)

        request = CreateLabResultRequest(
            order_id=order.id,
            patient_id=order.patient_id,
            doctor_id=order.doctor_id,
            file_url="s3://bucket/result.pdf",
            file_type="application/pdf",
        )

        response = await use_case.execute(request)

        assert response.status == LabResultStatus.PENDING
        assert response.file_url == "s3://bucket/result.pdf"
        assert len(result_repo._store) == 1

    async def test_raises_when_order_not_found(self, use_case):
        request = CreateLabResultRequest(
            order_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            file_url="s3://bucket/result.pdf",
            file_type="application/pdf",
        )
        with pytest.raises(LabOrderNotFoundError):
            await use_case.execute(request)

    async def test_each_result_has_unique_id(self, use_case, order_repo):
        order = make_lab_order()
        await order_repo.save(order)
        request = CreateLabResultRequest(
            order_id=order.id,
            patient_id=order.patient_id,
            doctor_id=order.doctor_id,
            file_url="s3://bucket/result.pdf",
            file_type="application/pdf",
        )
        r1 = await use_case.execute(request)
        r2 = await use_case.execute(request)
        assert r1.id != r2.id


# ---------------------------------------------------------------------------
# ListLabResultsUseCase
# ---------------------------------------------------------------------------


class TestListLabResults:
    @pytest.fixture
    def repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    @pytest.fixture
    def use_case(self, repo: FakeLabResultRepo) -> ListLabResultsUseCase:
        return ListLabResultsUseCase(result_repo=repo)

    async def test_patient_sees_only_published(self, use_case, repo):
        patient_id = uuid.uuid4()
        pending = make_lab_result(patient_id=patient_id, status=LabResultStatus.PENDING)
        published = make_lab_result(patient_id=patient_id, status=LabResultStatus.PUBLISHED)
        await repo.save(pending)
        await repo.save(published)

        results = await use_case.execute(caller_role="patient", patient_id=patient_id)
        assert len(results) == 1
        assert results[0].status == LabResultStatus.PUBLISHED

    async def test_doctor_sees_all_statuses(self, use_case, repo):
        patient_id = uuid.uuid4()
        for status in LabResultStatus:
            await repo.save(make_lab_result(patient_id=patient_id, status=status))

        results = await use_case.execute(caller_role="doctor", patient_id=patient_id)
        assert len(results) == len(list(LabResultStatus))

    async def test_filter_by_patient_id(self, use_case, repo):
        patient_id = uuid.uuid4()
        await repo.save(make_lab_result(patient_id=patient_id, status=LabResultStatus.PENDING))
        await repo.save(make_lab_result(patient_id=uuid.uuid4(), status=LabResultStatus.PENDING))

        results = await use_case.execute(caller_role="doctor", patient_id=patient_id)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# GetLabResultUseCase
# ---------------------------------------------------------------------------


class TestGetLabResult:
    @pytest.fixture
    def repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    @pytest.fixture
    def use_case(self, repo: FakeLabResultRepo) -> GetLabResultUseCase:
        return GetLabResultUseCase(result_repo=repo)

    async def test_doctor_can_get_any_result(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.AI_DRAFT)
        await repo.save(result)

        response = await use_case.execute(result_id=result.id, caller_role="doctor")
        assert response.id == result.id

    async def test_patient_can_get_published_result(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.PUBLISHED)
        await repo.save(result)

        response = await use_case.execute(result_id=result.id, caller_role="patient")
        assert response.status == LabResultStatus.PUBLISHED

    async def test_patient_denied_non_published(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.DOCTOR_REVIEW)
        await repo.save(result)

        with pytest.raises(ResultNotAccessibleError):
            await use_case.execute(result_id=result.id, caller_role="patient")

    async def test_not_found_raises_error(self, use_case):
        with pytest.raises(LabResultNotFoundError):
            await use_case.execute(result_id=uuid.uuid4(), caller_role="doctor")


# ---------------------------------------------------------------------------
# UpdateAIDraftUseCase
# ---------------------------------------------------------------------------


class TestUpdateAIDraft:
    @pytest.fixture
    def repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    @pytest.fixture
    def order_repo(self) -> FakeLabOrderRepo:
        return FakeLabOrderRepo()

    @pytest.fixture
    def use_case(self, repo: FakeLabResultRepo, order_repo: FakeLabOrderRepo) -> UpdateAIDraftUseCase:
        return UpdateAIDraftUseCase(result_repo=repo, order_repo=order_repo)

    async def test_applies_ai_draft_and_moves_to_doctor_review(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.PENDING)
        await repo.save(result)

        response = await use_case.execute(
            result_id=result.id,
            request=UpdateAIDraftRequest(
                ai_visual_findings={"summary": "normal"},
                ai_draft_text="Draft interpretation",
                ai_confidence=0.91,
                ai_draft_citations={"source": "guideline"},
                ai_model_versions={"llm": "groq-1"},
            ),
        )

        saved = await repo.get_by_id(result.id)
        assert response.status == LabResultStatus.DOCTOR_REVIEW
        assert saved.status == LabResultStatus.DOCTOR_REVIEW
        assert saved.ai_draft_text == "Draft interpretation"
        assert saved.ai_visual_findings == {"summary": "normal"}
        assert saved.ai_confidence == pytest.approx(0.91)
        assert saved.ai_draft_citations == {"source": "guideline"}
        assert saved.ai_model_versions == {"llm": "groq-1"}
        assert saved.ai_processed_at is not None

    async def test_allows_ai_draft_overwrite_for_idempotent_retry(self, use_case, repo):
        result = make_lab_result(
            status=LabResultStatus.AI_DRAFT,
            ai_draft_text="Old draft",
            ai_confidence=0.2,
        )
        await repo.save(result)

        response = await use_case.execute(
            result_id=result.id,
            request=UpdateAIDraftRequest(
                ai_draft_text="New draft",
                ai_confidence=0.99,
            ),
        )

        saved = await repo.get_by_id(result.id)
        assert response.status == LabResultStatus.DOCTOR_REVIEW
        assert saved.ai_draft_text == "New draft"
        assert saved.ai_confidence == pytest.approx(0.99)

    async def test_raises_when_result_not_found(self, use_case):
        with pytest.raises(LabResultNotFoundError):
            await use_case.execute(
                result_id=uuid.uuid4(),
                request=UpdateAIDraftRequest(ai_draft_text="Missing", ai_confidence=0.1),
            )

    async def test_rejects_invalid_status(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.PUBLISHED)
        await repo.save(result)

        with pytest.raises(ValueError, match="Expected PENDING or AI_PROCESSING"):
            await use_case.execute(
                result_id=result.id,
                request=UpdateAIDraftRequest(ai_draft_text="Invalid", ai_confidence=0.3),
            )


# ---------------------------------------------------------------------------
# GetLabReadinessUseCase
# ---------------------------------------------------------------------------


class TestGetLabReadiness:
    @pytest.fixture
    def order_repo(self) -> FakeLabOrderRepo:
        return FakeLabOrderRepo()

    @pytest.fixture
    def result_repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    @pytest.fixture
    def use_case(self, order_repo: FakeLabOrderRepo, result_repo: FakeLabResultRepo) -> GetLabReadinessUseCase:
        return GetLabReadinessUseCase(order_repo=order_repo, result_repo=result_repo)

    async def test_returns_all_ready_when_no_orders(self, use_case):
        appointment_id = uuid.uuid4()

        response = await use_case.execute(appointment_id)

        assert response == {
            "appointment_id": str(appointment_id),
            "total_orders": 0,
            "completed_results": 0,
            "all_ready": True,
            "results": [],
        }

    async def test_counts_partial_readiness(self, use_case, order_repo, result_repo):
        appointment_id = uuid.uuid4()
        order_one = make_lab_order(appointment_id=appointment_id)
        order_two = make_lab_order(appointment_id=appointment_id)
        await order_repo.save(order_one)
        await order_repo.save(order_two)

        await result_repo.save(
            make_lab_result(order_id=order_one.id, status=LabResultStatus.PUBLISHED)
        )
        await result_repo.save(
            make_lab_result(order_id=order_two.id, status=LabResultStatus.DOCTOR_REVIEW)
        )

        response = await use_case.execute(appointment_id)

        assert response["total_orders"] == 2
        assert response["completed_results"] == 1
        assert response["all_ready"] is False
        assert {item["order_id"] for item in response["results"]} == {
            str(order_one.id),
            str(order_two.id),
        }

    async def test_marks_all_ready_when_every_order_has_published_result(self, use_case, order_repo, result_repo):
        appointment_id = uuid.uuid4()
        orders = [make_lab_order(appointment_id=appointment_id) for _ in range(2)]
        for order in orders:
            await order_repo.save(order)
            await result_repo.save(make_lab_result(order_id=order.id, status=LabResultStatus.PUBLISHED))

        response = await use_case.execute(appointment_id)

        assert response["total_orders"] == 2
        assert response["completed_results"] == 2
        assert response["all_ready"] is True


# ---------------------------------------------------------------------------
# TestType enum — X-ray variants
# ---------------------------------------------------------------------------


class TestXrayTestTypes:
    @pytest.mark.parametrize("member", [
        TestType.BONE_XRAY,
        TestType.ABDOMINAL_XRAY,
        TestType.SKULL_XRAY,
        TestType.SPINE_XRAY,
        TestType.CHEST_XRAY,
    ])
    def test_xray_test_type_values_are_lowercase_strings(self, member):
        assert isinstance(member.value, str)
        assert member.value == member.value.lower()

    @pytest.mark.parametrize("expected_value,expected_member", [
        ("bone_xray", TestType.BONE_XRAY),
        ("abdominal_xray", TestType.ABDOMINAL_XRAY),
        ("skull_xray", TestType.SKULL_XRAY),
        ("spine_xray", TestType.SPINE_XRAY),
        ("chest_xray", TestType.CHEST_XRAY),
    ])
    def test_xray_test_type_from_value(self, expected_value, expected_member):
        assert TestType(expected_value) == expected_member

    def test_test_type_all_members(self):
        """Ensure new X-ray types are included alongside original types."""
        all_values = {t.value for t in TestType}
        required = {
            "blood_panel", "imaging", "ecg", "urine", "other",
            "bone_xray", "abdominal_xray", "skull_xray", "spine_xray", "chest_xray",
        }
        assert required.issubset(all_values), f"Missing: {required - all_values}"

    def test_test_type_is_str_enum(self):
        """TestType must be usable as a plain string for database storage."""
        for member in TestType:
            assert isinstance(member, str)
            assert member.value == member.value
