"""
Unit tests for infrastructure/celery/tasks.py

Tests the analyze_lab_task logic by:
  - Patching the LLM/clinical clients with Fakes
  - Using task.apply() to run synchronously without a broker
  - Verifying success and error propagation paths
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from Domain.entities import LabAnalysisResult


# Minimal valid payload for task invocation
BASE_PAYLOAD = {
    "result_id":  "r-001",
    "patient_id": "p-001",
    "file_url":   "http://example.com/xray.jpg",
    "input_type": "tabular",
    "department": "hematology",
    "test_name":  "CBC Panel",
    "tabular_data": {"wbc": 7.2, "rbc": 4.1},
    "auth_token": "internal-token-xyz",
}


def _make_mock_result(**kwargs):
    defaults = {
        "result_id": "r-001",
        "visual_findings": {"impression": "normal"},
        "draft_text": "AI draft text",
        "confidence": 0.85,
        "citations": [],
        "model_versions": {"vision": "gemini-1.5-flash", "text": "llama-3.3-70b-versatile"},
    }
    defaults.update(kwargs)
    return LabAnalysisResult(**defaults)


# ---------------------------------------------------------------------------
# Task execution tests
# ---------------------------------------------------------------------------

def test_analyze_lab_task_success():
    """Task completes and calls patch_ai_draft with correct data."""
    mock_result = _make_mock_result()

    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.GeminiClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.LabAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = AsyncMock(return_value=mock_result)
        MockEmrClient.return_value.patch_ai_draft = AsyncMock()

        from infrastructure.celery.tasks import analyze_lab_task
        task_result = analyze_lab_task.apply(args=[BASE_PAYLOAD])

    assert task_result.successful()
    MockEmrClient.return_value.patch_ai_draft.assert_called_once()

    # Verify the patch call has the correct fields
    call_args = MockEmrClient.return_value.patch_ai_draft.call_args
    draft_dict = call_args[0][1]  # positional arg 1 = draft payload dict
    assert draft_dict["ai_draft_text"] == "AI draft text"
    assert draft_dict["ai_confidence"] == pytest.approx(0.85)
    assert draft_dict["status"] == "AI_DRAFT"


def test_analyze_lab_task_passes_service_role_to_patch():
    """patch_ai_draft is called with x_user_role='service' (not an auth token)."""
    mock_result = _make_mock_result()

    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.GeminiClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.LabAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = AsyncMock(return_value=mock_result)
        MockEmrClient.return_value.patch_ai_draft = AsyncMock()

        from infrastructure.celery.tasks import analyze_lab_task
        analyze_lab_task.apply(args=[BASE_PAYLOAD])

    call_args = MockEmrClient.return_value.patch_ai_draft.call_args
    # x_user_role is passed as keyword argument
    assert call_args.kwargs.get("x_user_role") == "service"


def test_analyze_lab_task_constructs_request_from_payload():
    """LabAnalysisRequest is built with correct fields from payload dict."""
    from Domain.enums import InputType, Department

    captured_request = []

    async def fake_execute(request):
        await asyncio.sleep(0)
        captured_request.append(request)
        return _make_mock_result()

    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.GeminiClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.LabAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = fake_execute
        MockEmrClient.return_value.patch_ai_draft = AsyncMock()

        from infrastructure.celery.tasks import analyze_lab_task
        payload = {
            **BASE_PAYLOAD,
            "input_type": "tabular",
            "department": "respiratory",
            "test_name": "Spirometry",
        }
        analyze_lab_task.apply(args=[payload])

    req = captured_request[0]
    assert req.result_id == "r-001"
    assert req.input_type == InputType.TABULAR
    assert req.department == Department.RESPIRATORY
    assert req.test_name == "Spirometry"


def test_analyze_lab_task_retries_on_exception():
    """When execute raises, Celery task should propagate or retry (max_retries=2)."""
    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.GeminiClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.LabAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient"),
    ):
        MockUseCase.return_value.execute = AsyncMock(
            side_effect=RuntimeError("LLM unavailable")
        )

        from infrastructure.celery.tasks import analyze_lab_task
        # apply() with throw=False won't re-raise; check state instead
        task_result = analyze_lab_task.apply(args=[BASE_PAYLOAD], throw=False)

    # Should be FAILURE after retries exhausted
    assert task_result.failed()


def test_analyze_lab_task_patches_manual_review_after_all_retries():
    """After max retries exhausted, fallback patch marks result as requires_specialist_review=True."""
    fallback_calls = []

    async def fake_patch_ai_draft(result_id, draft, **kwargs):
        fallback_calls.append((result_id, draft))

    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.GeminiClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.LabAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = AsyncMock(
            side_effect=RuntimeError("LLM permanently down")
        )
        MockEmrClient.return_value.patch_ai_draft = fake_patch_ai_draft

        from infrastructure.celery.tasks import analyze_lab_task
        analyze_lab_task.apply(args=[BASE_PAYLOAD], throw=False)

    # The fallback must have been called with requires_specialist_review=True
    assert len(fallback_calls) >= 1
    last_result_id, last_draft = fallback_calls[-1]
    assert last_result_id == BASE_PAYLOAD["result_id"]
    assert last_draft.get("requires_specialist_review") is True
    assert last_draft.get("ai_confidence") == pytest.approx(0.0)


def test_analyze_lab_task_fallback_patch_fails_gracefully():
    """If the fallback patch itself raises, the task still fails cleanly without another exception."""
    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.GeminiClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.LabAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = AsyncMock(
            side_effect=RuntimeError("LLM permanently down")
        )
        MockEmrClient.return_value.patch_ai_draft = AsyncMock(
            side_effect=ConnectionError("EMR service unreachable")
        )

        from infrastructure.celery.tasks import analyze_lab_task
        # Should not raise an unexpected exception; just mark as failed
        task_result = analyze_lab_task.apply(args=[BASE_PAYLOAD], throw=False)

    assert task_result.failed()


# ===========================================================================
# analyze_all_labs_task
# ===========================================================================

BASE_HOLISTIC_PAYLOAD = {
    "appointment_id": "appt-001",
    "patient_id": "pat-001",
    "summary_id": "sum-001",
}


def _make_holistic_result(**kwargs):
    from Domain.entities import AllLabsAnalysisResult
    defaults = {
        "summary_id": "sum-001",
        "holistic_text": "⚠️ AI HOLISTIC DRAFT — patient looks healthy overall.",
        "status": "DONE",
    }
    defaults.update(kwargs)
    return AllLabsAnalysisResult(**defaults)


def test_analyze_all_labs_task_success():
    """Task completes and patches holistic summary with DONE status."""
    mock_result = _make_holistic_result()

    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.AllLabsAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = AsyncMock(return_value=mock_result)
        MockEmrClient.return_value.patch_holistic_summary = AsyncMock()

        from infrastructure.celery.tasks import analyze_all_labs_task
        task_result = analyze_all_labs_task.apply(args=[BASE_HOLISTIC_PAYLOAD])

    assert task_result.successful()
    assert MockEmrClient.return_value.patch_holistic_summary.call_count >= 1

    # Verify the final PATCH contains DONE status
    calls = MockEmrClient.return_value.patch_holistic_summary.call_args_list
    final_call = calls[-1]
    final_payload = final_call[0][1]  # positional arg 1 = payload dict
    assert final_payload["status"] == "DONE"
    assert "HOLISTIC DRAFT" in final_payload["ai_holistic_text"]


def test_analyze_all_labs_task_marks_processing_first():
    """Task sends a PROCESSING patch before the LLM call."""
    mock_result = _make_holistic_result()
    processing_calls = []

    async def fake_patch(appointment_id, payload, **kwargs):
        processing_calls.append(payload.get("status"))

    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.AllLabsAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = AsyncMock(return_value=mock_result)
        MockEmrClient.return_value.patch_holistic_summary = fake_patch

        from infrastructure.celery.tasks import analyze_all_labs_task
        analyze_all_labs_task.apply(args=[BASE_HOLISTIC_PAYLOAD])

    # First patch must be PROCESSING
    assert "PROCESSING" in processing_calls


def test_analyze_all_labs_task_patches_failed_on_error():
    """When use case returns FAILED, task patches FAILED status."""
    mock_result = _make_holistic_result(status="FAILED", holistic_text="Could not complete analysis.")

    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.AllLabsAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = AsyncMock(return_value=mock_result)
        MockEmrClient.return_value.patch_holistic_summary = AsyncMock()

        from infrastructure.celery.tasks import analyze_all_labs_task
        task_result = analyze_all_labs_task.apply(args=[BASE_HOLISTIC_PAYLOAD])

    assert task_result.successful()
    calls = MockEmrClient.return_value.patch_holistic_summary.call_args_list
    final_payload = calls[-1][0][1]
    assert final_payload["status"] == "FAILED"


def test_analyze_all_labs_task_fails_when_use_case_raises():
    """Hard crash from use case causes task to fail (retried by Celery)."""
    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.AllLabsAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = AsyncMock(side_effect=RuntimeError("unexpected crash"))
        MockEmrClient.return_value.patch_holistic_summary = AsyncMock()

        from infrastructure.celery.tasks import analyze_all_labs_task
        task_result = analyze_all_labs_task.apply(args=[BASE_HOLISTIC_PAYLOAD], throw=False)

    assert task_result.failed()


def test_analyze_all_labs_task_passes_correct_appointment_id():
    """appointment_id, patient_id, summary_id are forwarded to the use case."""
    captured = []

    async def fake_execute(request):
        captured.append(request)
        return _make_holistic_result()

    with (
        patch("infrastructure.celery.tasks.WokuClient"),
        patch("infrastructure.celery.tasks.ClinicalClient"),
        patch("infrastructure.celery.tasks.AllLabsAnalysisUseCase") as MockUseCase,
        patch("infrastructure.celery.tasks.EmrResultClient") as MockEmrClient,
    ):
        MockUseCase.return_value.execute = fake_execute
        MockEmrClient.return_value.patch_holistic_summary = AsyncMock()

        payload = {"appointment_id": "A-99", "patient_id": "P-88", "summary_id": "S-77"}
        from infrastructure.celery.tasks import analyze_all_labs_task
        analyze_all_labs_task.apply(args=[payload])

    assert len(captured) == 1
    req = captured[0]
    assert req.appointment_id == "A-99"
    assert req.patient_id == "P-88"
    assert req.summary_id == "S-77"

