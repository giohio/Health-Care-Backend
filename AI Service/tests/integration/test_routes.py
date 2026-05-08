"""
Integration tests for all AI Service HTTP routes.

All external dependencies (Groq, Gemini, ClinicalClient, EmrResultClient,
Celery) are replaced via FastAPI dependency overrides or unittest.mock.patch.

Uses httpx.AsyncClient with ASGITransport — no real server is started.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from Domain.entities import PatientContext
from presentation.dependencies import get_symptom_usecase, get_emr_summary_usecase


# ---------------------------------------------------------------------------
# Fake use cases for dependency override
# ---------------------------------------------------------------------------

async def _fake_stream(*chunks):
    for chunk in chunks:
        yield chunk


class FakeSymptomUseCase:
    async def execute(self, request, x_user_id, x_user_role):
        yield "Gợi ý chuyên khoa: "
        yield "Hô hấp. "
        yield "Mức độ: Thường."


class FakeEmrUseCase:
    async def execute(self, request, token, x_user_id, x_user_role):
        yield "Tóm tắt bệnh nhân: "
        yield "Tăng huyết áp, đang điều trị."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def override_dependencies(app):
    """Replace all FastAPI dependencies with Fakes for every test in this module."""
    app.dependency_overrides[get_symptom_usecase] = lambda: FakeSymptomUseCase()
    app.dependency_overrides[get_emr_summary_usecase] = lambda: FakeEmrUseCase()
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /health tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ai_service"


# ---------------------------------------------------------------------------
# POST /symptom-check tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_symptom_check_returns_stream(client):
    resp = await client.post(
        "/symptom-check",
        json={"patient_id": "p-001", "symptoms": "Đau đầu dữ dội trong 3 ngày"},
        headers={"x-user-id": "u-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    content = resp.text
    assert "data: " in content
    assert "data: [DONE]" in content


@pytest.mark.asyncio
async def test_symptom_check_streams_use_case_chunks(client):
    resp = await client.post(
        "/symptom-check",
        json={"patient_id": "p-001", "symptoms": "Ho khan, sốt nhẹ. Khó thở khi gắng sức."},
        headers={"x-user-id": "u-001", "x-user-role": "patient"},
    )
    body = resp.text
    assert "Hô hấp" in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_symptom_check_missing_headers_returns_422(client):
    resp = await client.post(
        "/symptom-check",
        json={"patient_id": "p-001", "symptoms": "Đau ngực bên trái, khó thở."},
        # Missing x-user-id / x-user-role headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_symptom_check_accepts_short_symptoms(client):
    """Short follow-up answers (e.g. 'Có', 'Không') are now valid."""
    resp = await client.post(
        "/symptom-check",
        json={"patient_id": "p-001", "symptoms": "Đau"},
        headers={"x-user-id": "u-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_symptom_check_with_optional_fields(client):
    resp = await client.post(
        "/symptom-check",
        json={
            "patient_id": "p-001",
            "symptoms": "Mắt đỏ và đau nhiều ngày liên tục không thuyên giảm.",
            "duration": "5 ngày",
            "severity": "nặng",
        },
        headers={"x-user-id": "u-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /analyze-lab tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_lab_enqueues_task(client):
    with patch("presentation.routes.lab.analyze_lab_task") as mock_task:
        mock_task.delay = MagicMock(return_value=None)

        resp = await client.post(
            "/analyze-lab",
            json={
                "result_id":  "r-001",
                "patient_id": "p-001",
                "file_url":   "http://storage/xray.jpg",
                "input_type": "image",
                "department": "respiratory",
                "test_name":  "Chest X-Ray",
                "auth_token": "internal-token",
            },
            headers={"x-user-id": "svc-emr", "x-user-role": "internal"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["result_id"] == "r-001"
    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_lab_passes_payload_to_celery(client):
    """All payload fields must be forwarded to analyze_lab_task.delay."""
    captured = {}

    with patch("presentation.routes.lab.analyze_lab_task") as mock_task:
        def capture(payload):
            captured.update(payload)
        mock_task.delay = capture

        await client.post(
            "/analyze-lab",
            json={
                "result_id":    "r-tab-001",
                "patient_id":   "p-002",
                "file_url":     "",
                "input_type":   "tabular",
                "department":   "hematology",
                "test_name":    "CBC",
                "tabular_data": {"wbc": 7.5},
                "auth_token":   "tok-xyz",
            },
            headers={"x-user-id": "svc-emr", "x-user-role": "internal"},
        )

    assert captured["result_id"] == "r-tab-001"
    assert captured["input_type"] == "tabular"
    assert captured["tabular_data"] == {"wbc": 7.5}
    assert captured["auth_token"] == "tok-xyz"


@pytest.mark.asyncio
async def test_analyze_lab_missing_required_field_returns_422(client):
    with patch("presentation.routes.lab.analyze_lab_task") as mock_task:
        mock_task.delay = MagicMock()

        resp = await client.post(
            "/analyze-lab",
            json={
                # result_id missing
                "patient_id": "p-001",
                "file_url":   "http://storage/xray.jpg",
                "input_type": "image",
                "department": "respiratory",
                "test_name":  "Chest X-Ray",
                "auth_token": "token",
            },
            headers={"x-user-id": "svc", "x-user-role": "internal"},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /summarize-emr tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_emr_doctor_gets_stream(client):
    resp = await client.post(
        "/summarize-emr",
        json={"patient_id": "p-001"},
        headers={
            "authorization": "Bearer doctor-jwt-token",
            "x-user-id":     "d-001",
            "x-user-role":   "doctor",
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "data: " in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_summarize_emr_streams_use_case_output(client):
    resp = await client.post(
        "/summarize-emr",
        json={"patient_id": "p-001"},
        headers={
            "authorization": "Bearer doctor-jwt",
            "x-user-id":     "d-001",
            "x-user-role":   "doctor",
        },
    )
    assert "Tăng huyết áp" in resp.text


@pytest.mark.asyncio
async def test_summarize_emr_patient_role_returns_403(client):
    resp = await client.post(
        "/summarize-emr",
        json={"patient_id": "p-001"},
        headers={
            "authorization": "Bearer patient-jwt",
            "x-user-id":     "p-001",
            "x-user-role":   "patient",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_summarize_emr_admin_is_allowed(client):
    resp = await client.post(
        "/summarize-emr",
        json={"patient_id": "p-001"},
        headers={
            "authorization": "Bearer admin-jwt",
            "x-user-id":     "a-001",
            "x-user-role":   "admin",
        },
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_summarize_emr_missing_authorization_header_returns_422(client):
    resp = await client.post(
        "/summarize-emr",
        json={"patient_id": "p-001"},
        headers={
            # Missing 'authorization' header
            "x-user-id":   "d-001",
            "x-user-role": "doctor",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_summarize_emr_missing_body_returns_422(client):
    resp = await client.post(
        "/summarize-emr",
        json={},  # patient_id missing
        headers={
            "authorization": "Bearer doctor-jwt",
            "x-user-id":     "d-001",
            "x-user-role":   "doctor",
        },
    )
    assert resp.status_code == 422
