"""
Unit tests for the holistic AppointmentLabSummary feature in EMR Result Service:
  - AppointmentLabSummary entity
  - GetHolisticSummaryUseCase
  - UpdateHolisticSummaryUseCase
  - VerifyAndPublishUseCase holistic trigger in _check_all_results_ready
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from Application.dtos import UpdateHolisticSummaryRequest, VerifyLabResultRequest
from Application.exceptions import LabResultNotFoundError
from Application.use_cases.holistic_summary import (
    GetHolisticSummaryUseCase,
    UpdateHolisticSummaryUseCase,
)
from Application.use_cases.verify_and_publish import VerifyAndPublishUseCase
from Domain.entities.appointment_lab_summary import AppointmentLabSummary, AppointmentSummaryStatus
from Domain.interfaces.appointment_summary_repository import IAppointmentSummaryRepository
from Domain.value_objects.lab_result_status import LabResultStatus
from tests.conftest import (
    FakeClinicalClient,
    FakeLabOrderRepo,
    FakeLabResultRepo,
    FakeNotificationClient,
    make_lab_order,
    make_lab_result,
)

NOW = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fake AppointmentSummaryRepository
# ---------------------------------------------------------------------------

class FakeAppointmentSummaryRepo(IAppointmentSummaryRepository):
    def __init__(self):
        self._store: Dict[uuid.UUID, AppointmentLabSummary] = {}

    async def save(self, summary: AppointmentLabSummary) -> AppointmentLabSummary:
        self._store[summary.appointment_id] = summary
        return summary

    async def get_by_appointment_id(
        self, appointment_id: uuid.UUID
    ) -> Optional[AppointmentLabSummary]:
        return self._store.get(appointment_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_summary(
    appointment_id=None,
    patient_id=None,
    status=AppointmentSummaryStatus.PENDING,
    **kwargs,
) -> AppointmentLabSummary:
    return AppointmentLabSummary(
        id=uuid.uuid4(),
        appointment_id=appointment_id or uuid.uuid4(),
        patient_id=patient_id or uuid.uuid4(),
        status=status,
        ai_holistic_text=None,
        total_results=2,
        created_at=NOW,
        updated_at=NOW,
        **kwargs,
    )


class FakeAiServiceClient:
    def __init__(self):
        self.trigger_calls = []

    async def trigger_holistic_analysis(self, appointment_id, patient_id, summary_id, **kwargs):
        self.trigger_calls.append({
            "appointment_id": str(appointment_id),
            "patient_id": str(patient_id),
            "summary_id": str(summary_id),
        })


# ===========================================================================
# AppointmentLabSummary entity
# ===========================================================================

class TestAppointmentLabSummaryEntity:
    def test_default_status_is_pending(self):
        summary = AppointmentLabSummary(
            id=uuid.uuid4(),
            appointment_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
        )
        assert summary.status == AppointmentSummaryStatus.PENDING

    def test_status_constants(self):
        assert AppointmentSummaryStatus.PENDING == "PENDING"
        assert AppointmentSummaryStatus.PROCESSING == "PROCESSING"
        assert AppointmentSummaryStatus.DONE == "DONE"
        assert AppointmentSummaryStatus.FAILED == "FAILED"

    def test_ai_holistic_text_defaults_to_none(self):
        summary = AppointmentLabSummary(
            id=uuid.uuid4(),
            appointment_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
        )
        assert summary.ai_holistic_text is None

    def test_total_results_defaults_to_zero(self):
        summary = AppointmentLabSummary(
            id=uuid.uuid4(),
            appointment_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
        )
        assert summary.total_results == 0

    def test_can_set_done_status(self):
        summary = _make_summary()
        summary.status = AppointmentSummaryStatus.DONE
        assert summary.status == "DONE"


# ===========================================================================
# GetHolisticSummaryUseCase
# ===========================================================================

class TestGetHolisticSummaryUseCase:
    @pytest.mark.asyncio
    async def test_returns_response_when_found(self):
        repo = FakeAppointmentSummaryRepo()
        appointment_id = uuid.uuid4()
        summary = _make_summary(appointment_id=appointment_id, status=AppointmentSummaryStatus.DONE)
        summary.ai_holistic_text = "⚠️ AI HOLISTIC DRAFT — patient looks good."
        await repo.save(summary)

        use_case = GetHolisticSummaryUseCase(summary_repo=repo)
        result = await use_case.execute(appointment_id)

        assert result is not None
        assert result.status == "DONE"
        assert result.appointment_id == appointment_id
        assert "AI HOLISTIC DRAFT" in result.ai_holistic_text

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        repo = FakeAppointmentSummaryRepo()
        use_case = GetHolisticSummaryUseCase(summary_repo=repo)
        result = await use_case.execute(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_response_contains_all_fields(self):
        repo = FakeAppointmentSummaryRepo()
        appointment_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        summary = _make_summary(
            appointment_id=appointment_id,
            patient_id=patient_id,
            status=AppointmentSummaryStatus.PROCESSING,
        )
        summary.total_results = 3
        await repo.save(summary)

        use_case = GetHolisticSummaryUseCase(summary_repo=repo)
        result = await use_case.execute(appointment_id)

        assert result.patient_id == patient_id
        assert result.total_results == 3
        assert result.status == "PROCESSING"


# ===========================================================================
# UpdateHolisticSummaryUseCase
# ===========================================================================

class TestUpdateHolisticSummaryUseCase:
    @pytest.mark.asyncio
    async def test_updates_text_and_status_to_done(self):
        repo = FakeAppointmentSummaryRepo()
        appointment_id = uuid.uuid4()
        summary = _make_summary(appointment_id=appointment_id)
        await repo.save(summary)

        use_case = UpdateHolisticSummaryUseCase(summary_repo=repo)
        request = UpdateHolisticSummaryRequest(
            ai_holistic_text="Full analysis text here",
            status="DONE",
        )
        result = await use_case.execute(appointment_id, request)

        assert result.status == "DONE"
        assert result.ai_holistic_text == "Full analysis text here"

    @pytest.mark.asyncio
    async def test_updates_status_to_failed(self):
        repo = FakeAppointmentSummaryRepo()
        appointment_id = uuid.uuid4()
        await repo.save(_make_summary(appointment_id=appointment_id))

        use_case = UpdateHolisticSummaryUseCase(summary_repo=repo)
        request = UpdateHolisticSummaryRequest(
            ai_holistic_text="Analysis failed: LLM timeout",
            status="FAILED",
        )
        result = await use_case.execute(appointment_id, request)

        assert result.status == "FAILED"

    @pytest.mark.asyncio
    async def test_raises_not_found_when_summary_missing(self):
        repo = FakeAppointmentSummaryRepo()
        use_case = UpdateHolisticSummaryUseCase(summary_repo=repo)
        request = UpdateHolisticSummaryRequest(
            ai_holistic_text="text",
            status="DONE",
        )

        with pytest.raises(LabResultNotFoundError):
            await use_case.execute(uuid.uuid4(), request)  # summary not in repo

    @pytest.mark.asyncio
    async def test_persists_update_in_repo(self):
        repo = FakeAppointmentSummaryRepo()
        appointment_id = uuid.uuid4()
        await repo.save(_make_summary(appointment_id=appointment_id))

        use_case = UpdateHolisticSummaryUseCase(summary_repo=repo)
        await use_case.execute(
            appointment_id,
            UpdateHolisticSummaryRequest(ai_holistic_text="saved text", status="DONE"),
        )

        # Read back from repo
        saved = await repo.get_by_appointment_id(appointment_id)
        assert saved.ai_holistic_text == "saved text"
        assert saved.status == "DONE"


# ===========================================================================
# VerifyAndPublishUseCase — holistic trigger
# ===========================================================================

class TestVerifyAndPublishHolisticTrigger:
    """Tests for the _check_all_results_ready + holistic trigger path."""

    def _make_use_case(
        self,
        result_repo,
        order_repo,
        summary_repo=None,
        ai_client=None,
        publisher=None,
    ) -> VerifyAndPublishUseCase:
        return VerifyAndPublishUseCase(
            result_repo=result_repo,
            order_repo=order_repo,
            notification_client=FakeNotificationClient(),
            clinical_client=FakeClinicalClient(),
            event_publisher=publisher or MagicMock(publish=AsyncMock()),
            summary_repo=summary_repo,
            ai_service_client=ai_client,
        )

    @pytest.mark.asyncio
    async def test_creates_summary_and_triggers_ai_when_all_published(self):
        appointment_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()

        order = make_lab_order(
            appointment_id=appointment_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
        )
        result = make_lab_result(
            order_id=order.id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )

        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()
        await result_repo.save(result)
        await order_repo.save(order)

        summary_repo = FakeAppointmentSummaryRepo()
        ai_client = FakeAiServiceClient()
        publisher = MagicMock()
        publisher.publish = AsyncMock()

        use_case = self._make_use_case(
            result_repo, order_repo,
            summary_repo=summary_repo,
            ai_client=ai_client,
            publisher=publisher,
        )

        await use_case.execute(
            result.id,
            doctor_id,
            VerifyLabResultRequest(doctor_notes="OK", published_text="All clear"),
        )

        # Summary must have been created
        saved_summary = await summary_repo.get_by_appointment_id(appointment_id)
        assert saved_summary is not None
        assert saved_summary.status == AppointmentSummaryStatus.PENDING
        assert saved_summary.appointment_id == appointment_id

        # AI trigger must have been called
        assert len(ai_client.trigger_calls) == 1
        assert ai_client.trigger_calls[0]["appointment_id"] == str(appointment_id)

    @pytest.mark.asyncio
    async def test_does_not_trigger_holistic_when_partial_results(self):
        """Two orders, only one published → must NOT trigger holistic."""
        appointment_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()

        order1 = make_lab_order(appointment_id=appointment_id, patient_id=patient_id, doctor_id=doctor_id)
        order2 = make_lab_order(appointment_id=appointment_id, patient_id=patient_id, doctor_id=doctor_id)

        result1 = make_lab_result(
            order_id=order1.id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        # result2 stays PENDING — not submitted

        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()
        await result_repo.save(result1)
        await order_repo.save(order1)
        await order_repo.save(order2)

        summary_repo = FakeAppointmentSummaryRepo()
        ai_client = FakeAiServiceClient()
        publisher = MagicMock()
        publisher.publish = AsyncMock()

        use_case = self._make_use_case(
            result_repo, order_repo,
            summary_repo=summary_repo,
            ai_client=ai_client,
            publisher=publisher,
        )

        await use_case.execute(
            result1.id,
            doctor_id,
            VerifyLabResultRequest(doctor_notes="OK"),
        )

        # No holistic trigger — order2 still pending
        assert len(ai_client.trigger_calls) == 0
        saved = await summary_repo.get_by_appointment_id(appointment_id)
        assert saved is None

    @pytest.mark.asyncio
    async def test_skips_trigger_when_summary_already_done(self):
        """If existing summary is DONE, do not re-trigger."""
        appointment_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()

        order = make_lab_order(
            appointment_id=appointment_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
        )
        result = make_lab_result(
            order_id=order.id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )

        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()
        await result_repo.save(result)
        await order_repo.save(order)

        summary_repo = FakeAppointmentSummaryRepo()
        # Pre-seed a DONE summary — must not be re-triggered
        existing = _make_summary(
            appointment_id=appointment_id,
            patient_id=patient_id,
            status=AppointmentSummaryStatus.DONE,
        )
        existing.ai_holistic_text = "Existing analysis text."
        await summary_repo.save(existing)

        ai_client = FakeAiServiceClient()
        publisher = MagicMock()
        publisher.publish = AsyncMock()

        use_case = self._make_use_case(
            result_repo, order_repo,
            summary_repo=summary_repo,
            ai_client=ai_client,
            publisher=publisher,
        )

        await use_case.execute(
            result.id,
            doctor_id,
            VerifyLabResultRequest(doctor_notes="OK"),
        )

        # Must NOT have triggered a new analysis
        assert len(ai_client.trigger_calls) == 0

        # Existing summary must be unchanged
        final = await summary_repo.get_by_appointment_id(appointment_id)
        assert final.status == AppointmentSummaryStatus.DONE
        assert final.ai_holistic_text == "Existing analysis text."

    @pytest.mark.asyncio
    async def test_works_without_summary_repo(self):
        """When summary_repo is None, must not crash."""
        appointment_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()

        order = make_lab_order(
            appointment_id=appointment_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
        )
        result = make_lab_result(
            order_id=order.id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()
        await result_repo.save(result)
        await order_repo.save(order)

        publisher = MagicMock()
        publisher.publish = AsyncMock()

        # No summary_repo, no ai_client
        use_case = self._make_use_case(
            result_repo, order_repo,
            summary_repo=None,
            ai_client=None,
            publisher=publisher,
        )

        # Must not raise
        response = await use_case.execute(
            result.id,
            doctor_id,
            VerifyLabResultRequest(doctor_notes="OK"),
        )
        assert response.status == LabResultStatus.PUBLISHED

    @pytest.mark.asyncio
    async def test_summary_total_results_matches_order_count(self):
        """total_results in created summary must equal number of orders."""
        appointment_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        doctor_id = uuid.uuid4()

        orders = [
            make_lab_order(appointment_id=appointment_id, patient_id=patient_id, doctor_id=doctor_id)
            for _ in range(3)
        ]
        # All 3 results in DOCTOR_REVIEW (i.e., about to be published)
        results = [
            make_lab_result(
                order_id=o.id,
                patient_id=patient_id,
                doctor_id=doctor_id,
                status=LabResultStatus.PUBLISHED,  # pre-publish 2
            )
            for o in orders[:-1]  # 2 already published
        ]
        # Last result is being published now
        last_result = make_lab_result(
            order_id=orders[-1].id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )

        result_repo = FakeLabResultRepo()
        order_repo = FakeLabOrderRepo()
        for o in orders:
            await order_repo.save(o)
        for r in results:
            await result_repo.save(r)
        await result_repo.save(last_result)

        summary_repo = FakeAppointmentSummaryRepo()
        ai_client = FakeAiServiceClient()
        publisher = MagicMock()
        publisher.publish = AsyncMock()

        use_case = self._make_use_case(
            result_repo, order_repo,
            summary_repo=summary_repo,
            ai_client=ai_client,
            publisher=publisher,
        )

        await use_case.execute(
            last_result.id,
            doctor_id,
            VerifyLabResultRequest(doctor_notes="OK"),
        )

        saved = await summary_repo.get_by_appointment_id(appointment_id)
        assert saved is not None
        assert saved.total_results == 3
