"""Route-level integration tests for EMR Result Service using FastAPI TestClient."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from Application.dtos import LabOrderResponse, LabResultResponse
from Application.exceptions import (
    LabOrderNotFoundError,
    LabResultNotFoundError,
    ResultNotAccessibleError,
)
from Application.use_cases.create_lab_order import CreateLabOrderUseCase
from Application.use_cases.flag_manual_review import FlagManualReviewUseCase
from Application.use_cases.get_lab_results import GetLabResultUseCase, ListLabResultsUseCase
from Application.use_cases.list_lab_orders import ListLabOrdersUseCase
from Application.use_cases.upload_lab_result import UploadLabResultUseCase
from Application.use_cases.verify_and_publish import VerifyAndPublishUseCase
from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType
from fastapi import FastAPI
from presentation.dependencies import (
    get_create_order_use_case,
    get_flag_manual_review_use_case,
    get_list_orders_use_case,
    get_list_results_use_case,
    get_patient_service_client,
    get_result_use_case,
    get_upload_result_use_case,
    get_verify_publish_use_case,
)
from presentation.routes.emr import router

app = FastAPI()
app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "emr-result-service"}

NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

DOCTOR_ID = uuid.uuid4()
PATIENT_ID = uuid.uuid4()
ORDER_ID = uuid.uuid4()
RESULT_ID = uuid.uuid4()

DOCTOR_HEADERS = {
    "x-user-id": str(DOCTOR_ID),
    "x-user-role": "doctor",
}

PATIENT_HEADERS = {
    "x-user-id": str(PATIENT_ID),
    "x-user-role": "patient",
}


class FakePatientService:
    async def get_patient_name(self, patient_id):
        return None


def make_order_response(**kwargs) -> LabOrderResponse:
    defaults = dict(
        id=ORDER_ID,
        patient_id=PATIENT_ID,
        doctor_id=DOCTOR_ID,
        appointment_id=None,
        test_name="CBC",
        test_type=TestType.BLOOD_PANEL,
        department=None,
        instructions=None,
        priority=OrderPriority.ROUTINE,
        fee=0,
        ordered_at=NOW,
        created_at=None,
    )
    defaults.update(kwargs)
    return LabOrderResponse(**defaults)


def make_result_response(**kwargs) -> LabResultResponse:
    defaults = dict(
        id=RESULT_ID,
        order_id=ORDER_ID,
        patient_id=PATIENT_ID,
        doctor_id=DOCTOR_ID,
        status=LabResultStatus.PENDING,
        file_url="s3://bucket/result.pdf",
        file_type="application/pdf",
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
# /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_check(self):
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "emr-result-service"


# ---------------------------------------------------------------------------
# Lab Orders
# ---------------------------------------------------------------------------


class TestCreateLabOrderRoute:
    def test_doctor_creates_order(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=make_order_response())
        app.dependency_overrides[get_create_order_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/lab-orders",
                    headers=DOCTOR_HEADERS,
                    json={
                        "patient_id": str(PATIENT_ID),
                        "doctor_id": str(DOCTOR_ID),
                        "test_name": "CBC",
                    },
                )
            assert resp.status_code == 201
        finally:
            app.dependency_overrides.clear()

    def test_patient_cannot_create_order(self):
        with TestClient(app) as client:
            resp = client.post(
                "/lab-orders",
                headers=PATIENT_HEADERS,
                json={
                    "patient_id": str(PATIENT_ID),
                    "doctor_id": str(DOCTOR_ID),
                    "test_name": "CBC",
                },
            )
        assert resp.status_code == 403

    def test_missing_headers_returns_401(self):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/lab-orders",
                json={"patient_id": str(PATIENT_ID), "doctor_id": str(DOCTOR_ID), "test_name": "CBC"},
            )
        assert resp.status_code == 401


class TestListLabOrdersRoute:
    def test_doctor_lists_orders(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[make_order_response()])
        app.dependency_overrides[get_list_orders_use_case] = lambda: mock_uc
        app.dependency_overrides[get_patient_service_client] = lambda: FakePatientService()
        try:
            with TestClient(app) as client:
                resp = client.get("/lab-orders", headers=DOCTOR_HEADERS)
            assert resp.status_code == 200
            assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()

    def test_list_orders_survives_patient_name_enrichment_failure(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[make_order_response()])

        class ExplodingPatientService:
            async def get_patient_name(self, patient_id):
                raise RuntimeError("patient service unavailable")

        app.dependency_overrides[get_list_orders_use_case] = lambda: mock_uc
        app.dependency_overrides[get_patient_service_client] = lambda: ExplodingPatientService()
        try:
            with TestClient(app) as client:
                resp = client.get("/lab-orders", headers=DOCTOR_HEADERS)
            assert resp.status_code == 200
            assert resp.json()[0]["patient_name"] is None
        finally:
            app.dependency_overrides.clear()

    def test_patient_list_forced_to_own_patient_id(self):
        """Patient request: even if ?patient_id passed, endpoint forces user's own id."""
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[make_order_response(patient_id=PATIENT_ID)])
        app.dependency_overrides[get_list_orders_use_case] = lambda: mock_uc
        app.dependency_overrides[get_patient_service_client] = lambda: FakePatientService()
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/lab-orders?patient_id={uuid.uuid4()}",
                    headers=PATIENT_HEADERS,
                )
            # Should succeed but with forced patient_id
            assert resp.status_code == 200
            call_kwargs = mock_uc.execute.call_args.kwargs
            assert call_kwargs["patient_id"] == PATIENT_ID
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Lab Results
# ---------------------------------------------------------------------------


class TestUploadLabResultRoute:
    def test_doctor_uploads_result(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=make_result_response())
        app.dependency_overrides[get_upload_result_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/lab-results",
                    headers=DOCTOR_HEADERS,
                    json={
                        "order_id": str(ORDER_ID),
                        "patient_id": str(PATIENT_ID),
                        "doctor_id": str(DOCTOR_ID),
                        "file_url": "s3://bucket/result.pdf",
                        "file_type": "application/pdf",
                    },
                )
            assert resp.status_code == 201
        finally:
            app.dependency_overrides.clear()

    def test_order_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=LabOrderNotFoundError())
        app.dependency_overrides[get_upload_result_use_case] = lambda: mock_uc
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/lab-results",
                    headers=DOCTOR_HEADERS,
                    json={
                        "order_id": str(uuid.uuid4()),
                        "patient_id": str(PATIENT_ID),
                        "doctor_id": str(DOCTOR_ID),
                        "file_url": "s3://bucket/result.pdf",
                        "file_type": "application/pdf",
                    },
                )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestGetLabResultRoute:
    def test_doctor_gets_any_result(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=make_result_response(status=LabResultStatus.AI_DRAFT))
        app.dependency_overrides[get_result_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.get(f"/lab-results/{RESULT_ID}", headers=DOCTOR_HEADERS)
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_patient_denied_non_published(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=ResultNotAccessibleError())
        app.dependency_overrides[get_result_use_case] = lambda: mock_uc
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(f"/lab-results/{RESULT_ID}", headers=PATIENT_HEADERS)
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=LabResultNotFoundError())
        app.dependency_overrides[get_result_use_case] = lambda: mock_uc
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(f"/lab-results/{uuid.uuid4()}", headers=DOCTOR_HEADERS)
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestVerifyAndPublishRoute:
    def test_doctor_verifies_result(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=make_result_response(status=LabResultStatus.PUBLISHED)
        )
        app.dependency_overrides[get_verify_publish_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.patch(
                    f"/lab-results/{RESULT_ID}/verify",
                    headers=DOCTOR_HEADERS,
                    json={"doctor_notes": "Verified OK."},
                )
            assert resp.status_code == 200
            assert resp.json()["status"] == "PUBLISHED"
        finally:
            app.dependency_overrides.clear()

    def test_invalid_status_transition_returns_422(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=ValueError("Cannot publish from PENDING"))
        app.dependency_overrides[get_verify_publish_use_case] = lambda: mock_uc
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.patch(
                    f"/lab-results/{RESULT_ID}/verify",
                    headers=DOCTOR_HEADERS,
                    json={},
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_patient_cannot_verify(self):
        with TestClient(app) as client:
            resp = client.patch(
                f"/lab-results/{RESULT_ID}/verify",
                headers=PATIENT_HEADERS,
                json={},
            )
        assert resp.status_code == 403


class TestFlagManualReviewRoute:
    def test_doctor_flags_result(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=make_result_response(status=LabResultStatus.NEEDS_MANUAL_REVIEW)
        )
        app.dependency_overrides[get_flag_manual_review_use_case] = lambda: mock_uc
        try:
            with TestClient(app) as client:
                resp = client.patch(
                    f"/lab-results/{RESULT_ID}/flag-manual",
                    headers=DOCTOR_HEADERS,
                )
            assert resp.status_code == 200
            assert resp.json()["status"] == "NEEDS_MANUAL_REVIEW"
        finally:
            app.dependency_overrides.clear()

    def test_patient_cannot_flag(self):
        with TestClient(app) as client:
            resp = client.patch(
                f"/lab-results/{RESULT_ID}/flag-manual",
                headers=PATIENT_HEADERS,
            )
        assert resp.status_code == 403

    def test_invalid_transition_returns_422(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=ValueError("Cannot flag PUBLISHED"))
        app.dependency_overrides[get_flag_manual_review_use_case] = lambda: mock_uc
        try:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.patch(
                    f"/lab-results/{RESULT_ID}/flag-manual",
                    headers=DOCTOR_HEADERS,
                )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()


class TestListLabResultsRoute:
    def test_doctor_lists_results(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[make_result_response()])
        app.dependency_overrides[get_list_results_use_case] = lambda: mock_uc
        app.dependency_overrides[get_patient_service_client] = lambda: FakePatientService()
        try:
            with TestClient(app) as client:
                resp = client.get("/lab-results", headers=DOCTOR_HEADERS)
            assert resp.status_code == 200
            assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()

    def test_list_results_survives_patient_name_enrichment_failure(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[make_result_response()])

        class ExplodingPatientService:
            async def get_patient_name(self, patient_id):
                raise RuntimeError("patient service unavailable")

        app.dependency_overrides[get_list_results_use_case] = lambda: mock_uc
        app.dependency_overrides[get_patient_service_client] = lambda: ExplodingPatientService()
        try:
            with TestClient(app) as client:
                resp = client.get("/lab-results", headers=DOCTOR_HEADERS)
            assert resp.status_code == 200
            assert resp.json()[0]["patient_name"] is None
        finally:
            app.dependency_overrides.clear()

    def test_patient_forced_to_own_id(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=[])
        app.dependency_overrides[get_list_results_use_case] = lambda: mock_uc
        app.dependency_overrides[get_patient_service_client] = lambda: FakePatientService()
        try:
            with TestClient(app) as client:
                resp = client.get(
                    f"/lab-results?patient_id={uuid.uuid4()}",
                    headers=PATIENT_HEADERS,
                )
            assert resp.status_code == 200
            call_kwargs = mock_uc.execute.call_args.kwargs
            assert call_kwargs["patient_id"] == PATIENT_ID
            assert call_kwargs["caller_role"] == "patient"
        finally:
            app.dependency_overrides.clear()
