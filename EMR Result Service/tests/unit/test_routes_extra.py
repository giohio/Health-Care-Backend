"""Additional route tests covering missing branches in emr.py.

Covers:
- POST /upload endpoint (unsupported_mime, empty_file, size_exceeded, generic ValueError)
- PATCH /lab-results/{id}/verify — LabResultNotFoundError → 404
- PATCH /lab-results/{id}/flag-manual — LabResultNotFoundError → 404
- _require_role with wrong role → 403
"""
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from Application.dtos import FileUploadResponse
from Application.exceptions import LabResultNotFoundError
from Application.use_cases.flag_manual_review import FlagManualReviewUseCase
from Application.use_cases.upload_file import UploadFileUseCase
from Application.use_cases.verify_and_publish import VerifyAndPublishUseCase
from Domain.value_objects.lab_result_status import LabResultStatus
from presentation.dependencies import (
    get_ai_service_client,
    get_flag_manual_review_use_case,
    get_order_repo,
    get_result_repo,
    get_result_use_case,
    get_upload_file_use_case,
    get_verify_publish_use_case,
)
from presentation.routes import emr as emr_module
from presentation.routes.emr import router
from unittest.mock import AsyncMock

app = FastAPI()
app.include_router(router)

DOCTOR_ID = uuid.uuid4()
PATIENT_ID = uuid.uuid4()
RESULT_ID = uuid.uuid4()

DOCTOR_HEADERS = {"x-user-id": str(DOCTOR_ID), "x-user-role": "doctor"}
PATIENT_HEADERS = {"x-user-id": str(PATIENT_ID), "x-user-role": "patient"}


def make_result_response(**kwargs):
    from Application.dtos import LabResultResponse
    from Domain.value_objects.order_priority import OrderPriority
    from Domain.value_objects.test_type import TestType

    ORDER_ID = uuid.uuid4()
    defaults = dict(
        id=RESULT_ID,
        order_id=ORDER_ID,
        patient_id=PATIENT_ID,
        doctor_id=DOCTOR_ID,
        status=LabResultStatus.PENDING,
        file_url="s3://bucket/result.pdf",
        file_type="pdf",
        ai_visual_findings=None,
        ai_draft_text=None,
        ai_confidence=None,
        ai_processed_at=None,
        published_text=None,
        published_findings=None,
        published_at=None,
        doctor_notes=None,
        verified_by=None,
        verified_at=None,
        created_at=None,
    )
    defaults.update(kwargs)
    return LabResultResponse(**defaults)


# ---------------------------------------------------------------------------
# Upload file endpoint error paths
# ---------------------------------------------------------------------------

class TestUploadFileRouteErrors:
    def _mock_upload_uc(self, side_effect):
        mock_uc = MagicMock(spec=UploadFileUseCase)
        mock_uc.execute.side_effect = side_effect
        app.dependency_overrides[get_upload_file_use_case] = lambda: mock_uc
        return mock_uc

    def test_unsupported_mime_returns_415(self):
        self._mock_upload_uc(ValueError("unsupported_mime:text/html"))
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/upload",
                    headers=DOCTOR_HEADERS,
                    files={"file": ("test.html", b"<html>", "text/html")},
                )
            assert resp.status_code == 415
        finally:
            app.dependency_overrides.clear()

    def test_empty_file_returns_400(self):
        self._mock_upload_uc(ValueError("empty_file"))
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/upload",
                    headers=DOCTOR_HEADERS,
                    files={"file": ("empty.pdf", b"", "application/pdf")},
                )
            assert resp.status_code == 400
            assert "No file content" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_size_exceeded_returns_400(self):
        self._mock_upload_uc(ValueError("size_exceeded:10"))
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/upload",
                    headers=DOCTOR_HEADERS,
                    files={"file": ("big.pdf", b"x" * 100, "application/pdf")},
                )
            assert resp.status_code == 400
            assert "10 MB" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_generic_value_error_returns_400(self):
        self._mock_upload_uc(ValueError("unexpected_error"))
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/upload",
                    headers=DOCTOR_HEADERS,
                    files={"file": ("f.pdf", b"data", "application/pdf")},
                )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_patient_cannot_upload(self):
        with TestClient(app) as client:
            resp = client.post(
                "/upload",
                headers=PATIENT_HEADERS,
                files={"file": ("f.pdf", b"data", "application/pdf")},
            )
        assert resp.status_code == 403

    def test_no_auth_header_returns_401(self):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/upload",
                files={"file": ("f.pdf", b"data", "application/pdf")},
            )
        assert resp.status_code == 401

    def test_successful_upload_returns_200(self):
        mock_uc = MagicMock(spec=UploadFileUseCase)
        mock_uc.execute.return_value = FileUploadResponse(
            url="http://storage/lab_results/abc.pdf",
            file_type="pdf",
            original_filename="result.pdf",
            size_bytes=4,
        )
        app.dependency_overrides[get_upload_file_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/upload",
                    headers=DOCTOR_HEADERS,
                    files={"file": ("result.pdf", b"data", "application/pdf")},
                )
            assert resp.status_code == 200
            assert resp.json()["file_type"] == "pdf"
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Verify and publish — not-found 404
# ---------------------------------------------------------------------------

class TestVerifyRouteNotFound:
    def test_lab_result_not_found_returns_404(self):
        mock_uc = MagicMock(spec=VerifyAndPublishUseCase)
        mock_uc.execute = AsyncMock(side_effect=LabResultNotFoundError())
        app.dependency_overrides[get_verify_publish_use_case] = lambda: mock_uc
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.patch(
                    f"/lab-results/{RESULT_ID}/verify",
                    headers=DOCTOR_HEADERS,
                    json={},
                )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Flag manual review — not-found 404
# ---------------------------------------------------------------------------

class TestFlagManualRouteNotFound:
    def test_lab_result_not_found_returns_404(self):
        mock_uc = MagicMock(spec=FlagManualReviewUseCase)
        mock_uc.execute = AsyncMock(side_effect=LabResultNotFoundError())
        app.dependency_overrides[get_flag_manual_review_use_case] = lambda: mock_uc
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.patch(
                    f"/lab-results/{RESULT_ID}/flag-manual",
                    headers=DOCTOR_HEADERS,
                )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Retry AI endpoint
# ---------------------------------------------------------------------------

class TestRetryAiRoute:
    def test_manual_doctor_review_is_retryable(self, monkeypatch):
        result_uc = MagicMock()
        result_uc.execute = AsyncMock(return_value=make_result_response(
            status=LabResultStatus.DOCTOR_REVIEW,
            file_type="manual",
            file_url=None,
            ai_draft_text='[{"test_name":"WBC","value":"7.1"}]',
        ))

        result_entity = MagicMock()
        result_repo = MagicMock()
        result_repo.get_by_id = AsyncMock(return_value=result_entity)
        result_repo.save = AsyncMock(return_value=result_entity)

        order = MagicMock()
        order.department = "internal_medicine"
        order.test_name = "CBC"
        order_repo = MagicMock()
        order_repo.get_by_id = AsyncMock(return_value=order)

        ai_client = MagicMock()
        ai_client.trigger_lab_analysis = AsyncMock(return_value=None)

        monkeypatch.setattr(emr_module.asyncio, "create_task", lambda coro: coro.close())

        app.dependency_overrides[get_result_use_case] = lambda: result_uc
        app.dependency_overrides[get_result_repo] = lambda: result_repo
        app.dependency_overrides[get_order_repo] = lambda: order_repo
        app.dependency_overrides[get_ai_service_client] = lambda: ai_client

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    f"/lab-results/{RESULT_ID}/retry-ai",
                    headers={**DOCTOR_HEADERS, "authorization": "Bearer test-token"},
                )

            assert resp.status_code == 200
            assert resp.json()["message"] == "AI analysis re-triggered"
            result_entity.transition_to.assert_called_once_with(LabResultStatus.PENDING)
            result_repo.save.assert_awaited_once()
            ai_client.trigger_lab_analysis.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    def test_non_manual_doctor_review_is_not_retryable(self):
        result_uc = MagicMock()
        result_uc.execute = AsyncMock(return_value=make_result_response(
            status=LabResultStatus.DOCTOR_REVIEW,
            file_type="pdf",
            file_url="s3://bucket/result.pdf",
        ))

        app.dependency_overrides[get_result_use_case] = lambda: result_uc
        app.dependency_overrides[get_result_repo] = lambda: MagicMock()
        app.dependency_overrides[get_order_repo] = lambda: MagicMock()
        app.dependency_overrides[get_ai_service_client] = lambda: MagicMock()

        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    f"/lab-results/{RESULT_ID}/retry-ai",
                    headers={**DOCTOR_HEADERS, "authorization": "Bearer test-token"},
                )

            assert resp.status_code == 400
            assert "not in a retryable state" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()
