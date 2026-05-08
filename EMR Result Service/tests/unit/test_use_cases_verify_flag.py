"""Unit tests for VerifyAndPublishUseCase and FlagManualReviewUseCase."""
import uuid
from datetime import datetime, timezone

import pytest

from Application.dtos import VerifyLabResultRequest
from Application.exceptions import LabResultNotFoundError
from Application.use_cases.flag_manual_review import FlagManualReviewUseCase
from Application.use_cases.verify_and_publish import VerifyAndPublishUseCase
from Domain.value_objects.lab_result_status import LabResultStatus
from tests.conftest import (
    FakeClinicalClient,
    FakeLabOrderRepo,
    FakeLabResultRepo,
    FakeNotificationClient,
    make_lab_order,
    make_lab_result,
)

NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# VerifyAndPublishUseCase
# ---------------------------------------------------------------------------


class TestVerifyAndPublish:
    @pytest.fixture
    def order_repo(self) -> FakeLabOrderRepo:
        return FakeLabOrderRepo()

    @pytest.fixture
    def result_repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    @pytest.fixture
    def notif_client(self) -> FakeNotificationClient:
        return FakeNotificationClient()

    @pytest.fixture
    def clinical_client(self) -> FakeClinicalClient:
        return FakeClinicalClient()

    def make_use_case(self, order_repo, result_repo, notif_client, clinical_client) -> VerifyAndPublishUseCase:
        return VerifyAndPublishUseCase(
            result_repo=result_repo,
            order_repo=order_repo,
            notification_client=notif_client,
            clinical_client=clinical_client,
        )

    async def test_happy_path_publishes_result(
        self, order_repo, result_repo, notif_client, clinical_client
    ):
        doctor_id = uuid.uuid4()
        order = make_lab_order()
        await order_repo.save(order)

        result = make_lab_result(
            order_id=order.id,
            patient_id=order.patient_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        result.ai_draft_text = "Normal CBC results."
        await result_repo.save(result)

        use_case = self.make_use_case(order_repo, result_repo, notif_client, clinical_client)
        response = await use_case.execute(
            result_id=result.id,
            doctor_id=doctor_id,
            request=VerifyLabResultRequest(doctor_notes="Approved."),
        )

        assert response.status == LabResultStatus.PUBLISHED
        assert response.doctor_id == result.doctor_id

    async def test_publish_triggers_notification(
        self, order_repo, result_repo, notif_client, clinical_client
    ):
        order = make_lab_order()
        await order_repo.save(order)

        result = make_lab_result(
            order_id=order.id,
            patient_id=order.patient_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        await result_repo.save(result)

        use_case = self.make_use_case(order_repo, result_repo, notif_client, clinical_client)
        await use_case.execute(
            result_id=result.id,
            doctor_id=uuid.uuid4(),
            request=VerifyLabResultRequest(),
        )

        assert len(notif_client.calls) == 1
        assert notif_client.calls[0]["patient_id"] == order.patient_id

    async def test_publish_triggers_clinical_client(
        self, order_repo, result_repo, notif_client, clinical_client
    ):
        order = make_lab_order()
        await order_repo.save(order)

        result = make_lab_result(
            order_id=order.id,
            patient_id=order.patient_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        await result_repo.save(result)

        use_case = self.make_use_case(order_repo, result_repo, notif_client, clinical_client)
        await use_case.execute(
            result_id=result.id,
            doctor_id=uuid.uuid4(),
            request=VerifyLabResultRequest(),
        )

        assert len(clinical_client.calls) == 1
        assert clinical_client.calls[0]["patient_id"] == order.patient_id

    async def test_result_not_found_raises(
        self, order_repo, result_repo, notif_client, clinical_client
    ):
        use_case = self.make_use_case(order_repo, result_repo, notif_client, clinical_client)
        with pytest.raises(LabResultNotFoundError):
            await use_case.execute(
                result_id=uuid.uuid4(),
                doctor_id=uuid.uuid4(),
                request=VerifyLabResultRequest(),
            )

    async def test_publish_invalid_status_raises_value_error(
        self, order_repo, result_repo, notif_client, clinical_client
    ):
        result = make_lab_result(status=LabResultStatus.PENDING)
        await result_repo.save(result)

        use_case = self.make_use_case(order_repo, result_repo, notif_client, clinical_client)
        with pytest.raises(ValueError):
            await use_case.execute(
                result_id=result.id,
                doctor_id=uuid.uuid4(),
                request=VerifyLabResultRequest(),
            )

    async def test_published_text_overrides_ai_draft(
        self, order_repo, result_repo, notif_client, clinical_client
    ):
        order = make_lab_order()
        await order_repo.save(order)

        result = make_lab_result(
            order_id=order.id,
            patient_id=order.patient_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        result.ai_draft_text = "AI summary."
        await result_repo.save(result)

        use_case = self.make_use_case(order_repo, result_repo, notif_client, clinical_client)
        response = await use_case.execute(
            result_id=result.id,
            doctor_id=uuid.uuid4(),
            request=VerifyLabResultRequest(published_text="Doctor edited text."),
        )
        assert response.published_text == "Doctor edited text."

    async def test_result_persisted_as_published(
        self, order_repo, result_repo, notif_client, clinical_client
    ):
        order = make_lab_order()
        await order_repo.save(order)
        result = make_lab_result(
            order_id=order.id,
            patient_id=order.patient_id,
            status=LabResultStatus.NEEDS_MANUAL_REVIEW,
        )
        await result_repo.save(result)

        use_case = self.make_use_case(order_repo, result_repo, notif_client, clinical_client)
        await use_case.execute(
            result_id=result.id,
            doctor_id=uuid.uuid4(),
            request=VerifyLabResultRequest(),
        )

        stored = result_repo._store[result.id]
        assert stored.status == LabResultStatus.PUBLISHED


# ---------------------------------------------------------------------------
# FlagManualReviewUseCase
# ---------------------------------------------------------------------------


class TestFlagManualReview:
    @pytest.fixture
    def repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    @pytest.fixture
    def use_case(self, repo: FakeLabResultRepo) -> FlagManualReviewUseCase:
        return FlagManualReviewUseCase(result_repo=repo)

    async def test_flag_from_pending(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.PENDING)
        await repo.save(result)

        response = await use_case.execute(result_id=result.id)
        assert response.status == LabResultStatus.NEEDS_MANUAL_REVIEW

    async def test_flag_from_ai_processing(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.AI_PROCESSING)
        await repo.save(result)

        response = await use_case.execute(result_id=result.id)
        assert response.status == LabResultStatus.NEEDS_MANUAL_REVIEW

    async def test_flag_from_ai_draft(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.AI_DRAFT)
        await repo.save(result)

        response = await use_case.execute(result_id=result.id)
        assert response.status == LabResultStatus.NEEDS_MANUAL_REVIEW

    async def test_flag_from_published_raises_value_error(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.PUBLISHED)
        await repo.save(result)

        with pytest.raises(ValueError):
            await use_case.execute(result_id=result.id)

    async def test_not_found_raises(self, use_case):
        with pytest.raises(LabResultNotFoundError):
            await use_case.execute(result_id=uuid.uuid4())

    async def test_persisted_after_flag(self, use_case, repo):
        result = make_lab_result(status=LabResultStatus.PENDING)
        await repo.save(result)
        await use_case.execute(result_id=result.id)

        stored = repo._store[result.id]
        assert stored.status == LabResultStatus.NEEDS_MANUAL_REVIEW
