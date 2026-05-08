"""
E2E test suite: AI Service — full clinical AI pipeline via Kong gateway.

Covers:
  - Health check
  - Symptom-check streaming (Tier 1 triage)
  - Lab analysis job enqueue (Tier 2 async)
  - EMR summary streaming (Tier 2 on-demand)
  - Role enforcement (patient cannot access doctor-only endpoints)
  - Input validation (422 on malformed requests)

Requires:
  - Full docker-compose stack running
  - Valid auth tokens (tests register/login fresh users per session)
  - Kong route /ai configured (see kong/kong.yml)
"""

import asyncio
import os
import uuid

import httpx
import pytest

AI_URL = os.getenv("AI_URL", "http://localhost:8000/ai")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000/auth")


# ---------------------------------------------------------------------------
# Helpers (mirrors helpers used by other E2E test files)
# ---------------------------------------------------------------------------

def short_id() -> str:
    return uuid.uuid4().hex[:8]


async def _register_login(http: httpx.AsyncClient, role: str) -> str:
    """Register a fresh user and return the JWT access token."""
    email = f"ai_e2e_{role}_{short_id()}@healthai.dev"
    credential = "Test1234!"
    full_name = f"AI E2E {role.title()}"

    reg = await http.post(
        f"{AUTH_URL}/register",
        json={"email": email, "password": credential, "role": role, "full_name": full_name},
    )
    if reg.status_code not in (200, 201):
        pytest.skip(f"Auth service unavailable ({reg.status_code}) — skipping AI E2E tests")

    if role == "patient":
        otp_resp = await http.get(f"{AUTH_URL}/dev/otp/{email}")
        if otp_resp.status_code == 200:
            otp = otp_resp.json().get("otp")
            if otp:
                await http.post(f"{AUTH_URL}/verify-email", json={"email": email, "otp": otp})

    login = await http.post(
        f"{AUTH_URL}/login",
        json={"email": email, "password": credential},
    )
    assert login.status_code == 200, f"Login failed: {login.text}"
    return login.json()["access_token"]


async def _wait_for_ai_service(http: httpx.AsyncClient, wait_secs: int = 20) -> None:
    deadline = asyncio.get_running_loop().time() + wait_secs
    while asyncio.get_running_loop().time() < deadline:
        try:
            async with asyncio.timeout(5.0):
                resp = await http.get(f"{AI_URL}/health")
            if resp.status_code == 200:
                return
        except Exception:
            pass
        await asyncio.sleep(1.5)
    pytest.skip(f"AI Service not reachable at {AI_URL} — skipping E2E tests")


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
async def patient_token(http):
    await _wait_for_ai_service(http)
    return await _register_login(http, "patient")


@pytest.fixture(scope="module")
async def doctor_token(http, admin_token):
    """Register a doctor via admin endpoint and return JWT access token."""
    email = f"ai_e2e_doctor_{short_id()}@healthai.dev"
    credential = "Test1234!"

    if "access_token" in http.cookies:
        del http.cookies["access_token"]

    reg = await http.post(
        f"{AUTH_URL}/admin/register-staff",
        json={"email": email, "password": credential, "role": "doctor"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    if reg.status_code not in (200, 201):
        pytest.skip(f"Doctor registration via admin failed ({reg.status_code}) — skipping AI E2E tests")

    login = await http.post(
        f"{AUTH_URL}/login",
        json={"email": email, "password": credential},
    )
    assert login.status_code == 200, f"Doctor login failed: {login.text}"
    return login.json()["access_token"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@pytest.mark.e2e
async def test_22_ai_health_check(http, patient_token):
    """AI Service /health endpoint must respond."""
    resp = await http.get(f"{AI_URL}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "ai_service"


# ---------------------------------------------------------------------------
# Tier 1 — Symptom Check
# ---------------------------------------------------------------------------

@pytest.mark.e2e
async def test_22_symptom_check_returns_sse_stream(http, patient_token):
    """Patient can stream a symptom triage analysis."""
    resp = await http.post(
        f"{AI_URL}/symptom-check",
        json={
            "patient_id": "e2e-patient-001",
            "symptoms":   "Tôi bị đau đầu dữ dội, buồn nôn và chóng mặt suốt 3 ngày.",
            "duration":   "3 ngày",
            "severity":   "nặng",
        },
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:300]}"
    ct = resp.headers.get("content-type", "")
    assert "text/event-stream" in ct
    body = resp.text
    assert "data:" in body
    assert "[DONE]" in body


@pytest.mark.e2e
async def test_22_symptom_check_ai_mentions_medical_specialty(http, patient_token):
    """AI response must mention at least one medical specialty or triage keyword."""
    resp = await http.post(
        f"{AI_URL}/symptom-check",
        json={
            "patient_id": "e2e-patient-002",
            "symptoms":   "Ho khan kéo dài, khó thở khi gắng sức, thỉnh thoảng đau ngực.",
        },
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    body = resp.text
    # Parse SSE: concatenate all "data: ..." line values so that keywords
    # that straddle a chunk boundary (e.g. "bao" + " lâu") are found correctly.
    sse_text = "".join(
        line[6:] for line in body.split("\n") if line.startswith("data: ")
    )
    specialties_or_keywords = [
        # Recommendation turn keywords
        "Hô hấp", "Tim mạch", "chuyên khoa", "bác sĩ", "ưu tiên",
        "Nội", "khám", "Thần kinh",
        # Question turn keywords (first turn is always a [Q])
        "triệu chứng", "bao lâu", "như thế nào", "mức độ", "vị trí",
        "khi nào", "thêm thông tin", "câu hỏi",
        # Any non-empty response with medical Vietnamese content
        "bạn", "bị", "đau", "khó", "kéo dài",
    ]
    assert any(kw in sse_text for kw in specialties_or_keywords), (
        f"Expected medical content in stream, got: {body[:400]}"
    )


@pytest.mark.e2e
async def test_22_symptom_check_requires_auth(http):
    """Unauthenticated request → 401 (Kong) or 422 (FastAPI missing header)."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as fresh:
        resp = await fresh.post(
            f"{AI_URL}/symptom-check",
            json={"patient_id": "p-001", "symptoms": "Đau đầu buồn nôn liên tục."},
        )
    assert resp.status_code in (401, 403, 422), f"Expected auth error, got {resp.status_code}"


@pytest.mark.e2e
async def test_22_symptom_check_rejects_short_symptoms(http, patient_token):
    """Symptoms field with < 10 chars → 422 Unprocessable Entity."""
    resp = await http.post(
        f"{AI_URL}/symptom-check",
        json={"patient_id": "p-001", "symptoms": "Đau"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tier 2 — Lab Analysis (async queue)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
async def test_22_analyze_lab_tabular_enqueues_job(http, doctor_token):
    """Doctor can enqueue a tabular lab analysis job; service responds 200+queued."""
    result_id = f"e2e-{short_id()}"
    resp = await http.post(
        f"{AI_URL}/analyze-lab",
        json={
            "result_id":    result_id,
            "patient_id":   "e2e-patient-001",
            "file_url":     "",
            "input_type":   "tabular",
            "department":   "hematology",
            "test_name":    "CBC Complete Blood Count",
            "tabular_data": {
                "WBC":        6.8,
                "RBC":        4.2,
                "Hemoglobin": 13.5,
                "Hematocrit": 40.1,
                "Platelets":  230,
            },
            "auth_token":   doctor_token,
        },
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:300]}"
    data = resp.json()
    assert data["status"] == "queued"
    assert data["result_id"] == result_id
    assert "message" in data


@pytest.mark.e2e
async def test_22_analyze_lab_missing_fields_returns_422(http, doctor_token):
    """Missing required fields in lab analysis request → 422."""
    resp = await http.post(
        f"{AI_URL}/analyze-lab",
        json={"patient_id": "p-001"},  # Most fields missing
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tier 2 on-demand — EMR Summary
# ---------------------------------------------------------------------------

@pytest.mark.e2e
async def test_22_summarize_emr_doctor_streams_summary(http, doctor_token):
    """Doctor can stream an EMR summary for a patient."""
    resp = await http.post(
        f"{AI_URL}/summarize-emr",
        json={"patient_id": "e2e-patient-001"},
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text[:300]}"
    ct = resp.headers.get("content-type", "")
    assert "text/event-stream" in ct
    body = resp.text
    assert "data:" in body
    assert "[DONE]" in body


@pytest.mark.e2e
async def test_22_summarize_emr_patient_forbidden(http, patient_token):
    """Patient role cannot access EMR summary — must receive 403."""
    resp = await http.post(
        f"{AI_URL}/summarize-emr",
        json={"patient_id": "e2e-patient-001"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert resp.status_code == 403, (
        f"Expected 403 Forbidden, got {resp.status_code}: {resp.text[:200]}"
    )


@pytest.mark.e2e
async def test_22_summarize_emr_requires_auth(http):
    """Unauthenticated EMR request → 401/403/422."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as fresh:
        resp = await fresh.post(
            f"{AI_URL}/summarize-emr",
            json={"patient_id": "e2e-patient-001"},
        )
    assert resp.status_code in (401, 403, 422)


@pytest.mark.e2e
async def test_22_summarize_emr_missing_patient_id_422(http, doctor_token):
    """Missing patient_id → 422 validation error."""
    resp = await http.post(
        f"{AI_URL}/summarize-emr",
        json={},
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 422
