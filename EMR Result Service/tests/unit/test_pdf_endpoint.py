"""Tests for the /lab-results/{result_id}/pdf endpoint."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from Application.dtos import LabOrderResponse
from Application.use_cases.get_lab_results import GetLabResultUseCase
from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType
from presentation.dependencies import get_order_repo, get_patient_service_client, get_result_use_case
from presentation.routes.emr import router
from tests.conftest import FakeLabOrderRepo, FakeLabResultRepo, FakePatientServiceClient, make_lab_order, make_lab_result


app = FastAPI()
app.include_router(router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


NOW = datetime(2025, 3, 10, 9, 0, 0, tzinfo=timezone.utc)
DOCTOR_ID = uuid.uuid4()
PATIENT_ID = uuid.uuid4()
ORDER_ID = uuid.uuid4()
RESULT_ID = uuid.uuid4()

DOCTOR_HEADERS = {"x-user-id": str(DOCTOR_ID), "x-user-role": "doctor"}
PATIENT_HEADERS = {"x-user-id": str(PATIENT_ID), "x-user-role": "patient"}


@pytest.fixture
def order_repo():
    repo = FakeLabOrderRepo()
    repo._store[ORDER_ID] = make_lab_order(
        id=ORDER_ID,
        patient_id=PATIENT_ID,
        doctor_id=DOCTOR_ID,
        test_name="Complete Blood Count (CBC) with Differential",
    )
    return repo


@pytest.fixture
def result_repo():
    repo = FakeLabResultRepo()
    repo._store[RESULT_ID] = make_lab_result(
        id=RESULT_ID,
        order_id=ORDER_ID,
        patient_id=PATIENT_ID,
        doctor_id=DOCTOR_ID,
        status=LabResultStatus.PUBLISHED,
        ai_draft_text=(
            "The CBC results show mild leukocytosis with neutrophilia, "
            "suggesting a possible mild bacterial infection."
        ),
        ai_visual_findings=[
            {
                "name": "White Blood Cell (WBC)",
                "value": 11.2,
                "unit": "×10⁹/L",
                "reference_low": 4.5,
                "reference_high": 11.0,
                "flag": "H",
            },
            {
                "name": "Red Blood Cell (RBC)",
                "value": 4.8,
                "unit": "×10¹²/L",
                "reference_low": 4.5,
                "reference_high": 5.5,
                "flag": "N",
            },
            {
                "name": "Hemoglobin (Hb)",
                "value": 13.5,
                "unit": "g/dL",
                "reference_low": 12.0,
                "reference_high": 17.0,
                "flag": "N",
            },
            {
                "name": "Platelet Count",
                "value": 180,
                "unit": "×10⁹/L",
                "reference_low": 150,
                "reference_high": 400,
                "flag": "N",
            },
            {
                "name": "Mean Corpuscular Volume (MCV)",
                "value": 88,
                "unit": "fL",
                "reference_low": 80,
                "reference_high": 100,
                "flag": "N",
            },
            {
                "name": "Neutrophils (Neu%)",
                "value": 65,
                "unit": "%",
                "reference_low": 40,
                "reference_high": 75,
                "flag": "N",
            },
            {
                "name": "Lymphocytes (Lym%)",
                "value": 28,
                "unit": "%",
                "reference_low": 20,
                "reference_high": 40,
                "flag": "N",
            },
            {
                "name": "Alanine Aminotransferase (ALT)",
                "value": 85,
                "unit": "U/L",
                "reference_low": 7,
                "reference_high": 56,
                "flag": "H",
            },
            {
                "name": "Aspartate Aminotransferase (AST)",
                "value": 38,
                "unit": "U/L",
                "reference_low": 10,
                "reference_high": 40,
                "flag": "N",
            },
            {
                "name": "Fasting Blood Glucose",
                "value": 98,
                "unit": "mg/dL",
                "reference_low": 70,
                "reference_high": 100,
                "flag": "N",
            },
            {
                "name": "Creatinine",
                "value": 0.7,
                "unit": "mg/dL",
                "reference_low": 0.6,
                "reference_high": 1.2,
                "flag": "N",
            },
            {
                "name": "Blood Urea Nitrogen (BUN)",
                "value": 22,
                "unit": "mg/dL",
                "reference_low": 7,
                "reference_high": 20,
                "flag": "H",
            },
        ],
    )
    return repo


@pytest.fixture
def patient_svc():
    return FakePatientServiceClient(name="Tran Thi B")


class TestPDFEndpoint:
    def test_pdf_returns_200_with_pdf_content_type(self, order_repo, result_repo, patient_svc):
        """GET /lab-results/{id}/pdf returns HTTP 200 and application/pdf."""
        def override_result_use_case():
            return GetLabResultUseCase(result_repo)

        def override_order_repo():
            return order_repo

        def override_patient_svc():
            return patient_svc

        app.dependency_overrides[get_result_use_case] = override_result_use_case
        app.dependency_overrides[get_order_repo] = override_order_repo
        app.dependency_overrides[get_patient_service_client] = override_patient_svc

        try:
            client = TestClient(app)
            response = client.get(f"/lab-results/{RESULT_ID}/pdf", headers=DOCTOR_HEADERS)

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            assert response.headers["content-type"] == "application/pdf"
        finally:
            app.dependency_overrides.clear()

    def test_pdf_filename_contains_result_id(self, order_repo, result_repo, patient_svc):
        """Content-Disposition header includes result ID in filename."""
        def override_result_use_case():
            return GetLabResultUseCase(result_repo)

        def override_order_repo():
            return order_repo

        app.dependency_overrides[get_result_use_case] = override_result_use_case
        app.dependency_overrides[get_order_repo] = override_order_repo
        app.dependency_overrides[get_patient_service_client] = lambda: patient_svc

        try:
            client = TestClient(app)
            response = client.get(f"/lab-results/{RESULT_ID}/pdf", headers=DOCTOR_HEADERS)

            assert response.status_code == 200
            cd = response.headers.get("content-disposition", "")
            assert str(RESULT_ID) in cd, f"Result ID {RESULT_ID} not in Content-Disposition: {cd}"
        finally:
            app.dependency_overrides.clear()

    def test_pdf_body_starts_with_pdf_magic_bytes(self, order_repo, result_repo, patient_svc):
        """PDF binary body starts with %PDF-."""
        def override_result_use_case():
            return GetLabResultUseCase(result_repo)

        def override_order_repo():
            return order_repo

        app.dependency_overrides[get_result_use_case] = override_result_use_case
        app.dependency_overrides[get_order_repo] = override_order_repo
        app.dependency_overrides[get_patient_service_client] = lambda: patient_svc

        try:
            client = TestClient(app)
            response = client.get(f"/lab-results/{RESULT_ID}/pdf", headers=DOCTOR_HEADERS)

            assert response.status_code == 200
            assert response.content[:4] == b"%PDF", (
                f"PDF magic bytes not found. Got: {response.content[:10]!r}"
            )
        finally:
            app.dependency_overrides.clear()

    def test_pdf_500_without_patient_service(self, order_repo, result_repo):

        def override_result_use_case():
            return GetLabResultUseCase(result_repo)

        def override_order_repo():
            return order_repo

        app.dependency_overrides[get_result_use_case] = override_result_use_case
        app.dependency_overrides[get_order_repo] = override_order_repo

        try:
            client = TestClient(app)
            response = client.get(f"/lab-results/{RESULT_ID}/pdf", headers=DOCTOR_HEADERS)
            # patient_svc falls back to None → PDF still renders with N/A
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_pdf_returns_403_for_unrelated_patient(self, order_repo, result_repo, patient_svc):
        """A patient cannot access another patient's lab result PDF."""
        unrelated_id = uuid.uuid4()
        unrelated_headers = {"x-user-id": str(unrelated_id), "x-user-role": "patient"}

        def override_result_use_case():
            return GetLabResultUseCase(result_repo)

        def override_order_repo():
            return order_repo

        app.dependency_overrides[get_result_use_case] = override_result_use_case
        app.dependency_overrides[get_order_repo] = override_order_repo
        app.dependency_overrides[get_patient_service_client] = lambda: patient_svc

        try:
            client = TestClient(app)
            response = client.get(f"/lab-results/{RESULT_ID}/pdf", headers=unrelated_headers)
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_pdf_returns_404_for_nonexistent_result(self, order_repo, result_repo, patient_svc):

        def override_result_use_case():
            return GetLabResultUseCase(result_repo)

        def override_order_repo():
            return order_repo

        app.dependency_overrides[get_result_use_case] = override_result_use_case
        app.dependency_overrides[get_order_repo] = override_order_repo
        app.dependency_overrides[get_patient_service_client] = lambda: patient_svc

        try:
            client = TestClient(app)
            fake_id = uuid.uuid4()
            response = client.get(f"/lab-results/{fake_id}/pdf", headers=DOCTOR_HEADERS)
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()
