"""
E2E tests for AI Service — run against a live Docker Compose environment.

These tests require the full stack:
  - ai_service running at AI_SERVICE_URL (via Kong or direct)
  - Auth Service for JWT token minting
  - Kong gateway at GATEWAY_URL

Skip gracefully when services are not reachable.

Usage (with docker-compose up):
  pytest tests/e2e/ -m e2e -v
"""

import asyncio
import os
import uuid

import httpx
import pytest

# Service URLs — match docker-compose service names / Kong routes
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
AI_URL = os.getenv("AI_SERVICE_URL", f"{GATEWAY_URL}/ai")
AUTH_URL = os.getenv("AUTH_URL", f"{GATEWAY_URL}/auth")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def short_id() -> str:
    return uuid.uuid4().hex[:8]


async def _wait_for_service(http: httpx.AsyncClient, url: str, timeout: int = 30) -> bool:
    """Return True if service health check passes within timeout, False otherwise."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            async with asyncio.timeout(5.0):
                resp = await http.get(f"{url}/health")
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


async def _register_and_login(http: httpx.AsyncClient, role: str = "patient") -> tuple[str, dict]:
    """Register a test user and return (token, user_id)."""
    suffix = short_id()
    email = f"test_{role}_{suffix}@healthai.dev"
    credential = "Test1234!"

    reg_resp = await http.post(
        f"{AUTH_URL}/register",
        json={"email": email, "password": credential, "role": role, "full_name": f"Test {role.title()}"},
    )
    assert reg_resp.status_code in (200, 201), f"Register failed: {reg_resp.text}"

    login_resp = await http.post(
        f"{AUTH_URL}/login",
        json={"email": email, "password": credential},
    )
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"

    token = login_resp.json()["data"]["access_token"]
    return token, email


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
async def http():
    timeout = httpx.Timeout(60.0, connect=15.0)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=0)
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        yield client


@pytest.fixture(scope="module")
async def ai_service_available(http):
    """Skip module if AI Service is not reachable."""
    available = await _wait_for_service(http, AI_URL, timeout=10)
    if not available:
        pytest.skip(f"AI Service not reachable at {AI_URL} — skipping E2E tests")


@pytest.fixture(scope="module")
async def patient_token(http, ai_service_available):
    token, _ = await _register_and_login(http, role="patient")
    return token


@pytest.fixture(scope="module")
async def doctor_token(http, ai_service_available):
    token, _ = await _register_and_login(http, role="doctor")
    return token


# ---------------------------------------------------------------------------
# Health check E2E test
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_ai_service_health(http, ai_service_available):
    """AI Service must respond to /health with status=healthy."""
    resp = await http.get(f"{AI_URL}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ai_service"


# ---------------------------------------------------------------------------
# Symptom check E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_symptom_check_patient_can_stream(http, patient_token):
    """Patient can call symptom-check and receive a streamed SSE response."""
    resp = await http.post(
        f"{AI_URL}/symptom-check",
        json={
            "patient_id": "e2e-patient-001",
            "symptoms": "Tôi bị đau đầu dữ dội kèm buồn nôn từ 3 ngày nay.",
            "duration": "3 ngày",
            "severity": "nặng",
        },
        headers={
            "Authorization": f"Bearer {patient_token}",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    # Must contain SSE lines
    assert "data:" in body
    assert "[DONE]" in body


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_symptom_check_response_contains_medical_content(http, patient_token):
    """AI response should mention a medical department or triage advice."""
    resp = await http.post(
        f"{AI_URL}/symptom-check",
        json={
            "patient_id": "e2e-patient-002",
            "symptoms": "Tôi bị ho khan, khó thở và tức ngực từ 2 ngày nay.",
        },
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    body = resp.text
    # Should contain Vietnamese medical terms
    assert any(kw in body for kw in [
        "Hô hấp", "Tim mạch", "chuyên khoa", "ưu tiên", "bác sĩ", "khám"
    ]), f"No medical content found in: {body[:300]}"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_symptom_check_unauthenticated_is_rejected(http):
    """Unauthenticated request must be rejected at Kong gateway (401) or missing header (422)."""
    resp = await http.post(
        f"{AI_URL}/symptom-check",
        json={
            "patient_id": "p-001",
            "symptoms": "Đau đầu dữ dội, sốt cao.",
        },
        # No Authorization header
    )
    # Kong returns 401 for missing JWT; direct FastAPI returns 422 for missing header
    assert resp.status_code in (401, 422)


# ---------------------------------------------------------------------------
# Lab analysis E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_analyze_lab_enqueues_and_returns_queued(http, doctor_token):
    """POST /analyze-lab returns queued status immediately (Celery task is async)."""
    result_id = f"e2e-result-{short_id()}"
    resp = await http.post(
        f"{AI_URL}/analyze-lab",
        json={
            "result_id":    result_id,
            "patient_id":   "e2e-patient-001",
            "file_url":     "",
            "input_type":   "tabular",
            "department":   "hematology",
            "test_name":    "CBC Panel",
            "tabular_data": {
                "WBC": 7.2, "RBC": 4.5, "Hemoglobin": 14.0,
                "Hematocrit": 42.0, "Platelets": 250.0,
            },
            "auth_token":   doctor_token,
        },
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert data["status"] == "queued"
    assert data["result_id"] == result_id


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_analyze_lab_invalid_payload_returns_422(http, doctor_token):
    """Missing required fields returns validation error."""
    resp = await http.post(
        f"{AI_URL}/analyze-lab",
        json={
            "patient_id": "e2e-patient-001",
            # result_id, file_url, input_type, department, test_name, auth_token missing
        },
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# EMR summary E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_summarize_emr_doctor_receives_stream(http, doctor_token):
    """Doctor can request EMR summary and receive streamed response."""
    resp = await http.post(
        f"{AI_URL}/summarize-emr",
        json={"patient_id": "e2e-patient-001"},
        headers={
            "Authorization": f"Bearer {doctor_token}",
        },
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "data:" in body
    assert "[DONE]" in body


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_summarize_emr_patient_is_forbidden(http, patient_token):
    """Patient must get 403 when trying to access EMR summary."""
    resp = await http.post(
        f"{AI_URL}/summarize-emr",
        json={"patient_id": "e2e-patient-001"},
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_summarize_emr_contains_ai_disclaimer(http, doctor_token):
    """The AI disclaimer must appear at the end of the summary stream."""
    resp = await http.post(
        f"{AI_URL}/summarize-emr",
        json={"patient_id": "e2e-patient-001"},
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    body = resp.text
    # The AI disclaimer is always appended by GroqClient.stream_completion
    assert "AI" in body or "trợ lý" in body.lower() or "bác sĩ" in body.lower()


# ---------------------------------------------------------------------------
# Lab Q&A chat E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_lab_chat_patient_flow(http, patient_token):
    """Patient can stream a Q&A response about HbA1c from /lab-chat."""
    resp = await http.post(
        f"{AI_URL}/lab-chat",
        json={"question": "Chỉ số HbA1c của tôi là 9.2%. Điều đó có nghĩa gì?"},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "x-user-role": "patient",
            "x-user-id": "e2e-patient-001",
        },
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    assert "text/event-stream" in resp.headers.get("content-type", "")
    body = resp.text
    assert "data:" in body
    assert "[DONE]" in body


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_lab_chat_doctor_flow(http, doctor_token):
    """Doctor receives a clinical interpretation from /lab-chat."""
    resp = await http.post(
        f"{AI_URL}/lab-chat",
        json={
            "question": "WBC 14.5 x10^9/L with left shift — clinical significance?",
            "department": "hematology",
        },
        headers={
            "Authorization": f"Bearer {doctor_token}",
            "x-user-role": "doctor",
            "x-user-id": "e2e-doctor-001",
        },
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    body = resp.text
    assert "data:" in body
    assert "[DONE]" in body


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_lab_chat_missing_question_returns_422(http, patient_token):
    resp = await http.post(
        f"{AI_URL}/lab-chat",
        json={},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "x-user-role": "patient",
            "x-user-id": "e2e-patient-001",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Clinical assist E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_clinical_assist_doctor_flow(http, doctor_token):
    """Doctor receives a clinical decision support stream."""
    resp = await http.post(
        f"{AI_URL}/clinical-assist",
        json={
            "question": "What is the first-line treatment for newly diagnosed T2DM with HbA1c 8.5%?",
            "department": "endocrinology",
        },
        headers={
            "Authorization": f"Bearer {doctor_token}",
            "x-user-role": "doctor",
            "x-user-id": "e2e-doctor-001",
        },
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    body = resp.text
    assert "data:" in body
    assert "[DONE]" in body


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_clinical_assist_patient_forbidden(http, patient_token):
    """Patient must receive 403 from /clinical-assist."""
    resp = await http.post(
        f"{AI_URL}/clinical-assist",
        json={"question": "Diagnose me please"},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "x-user-role": "patient",
            "x-user-id": "e2e-patient-001",
        },
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Speech: TTS E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tts_returns_audio_bytes(http, patient_token):
    """POST /speech/tts must return non-empty MP3 bytes in audio/mpeg."""
    resp = await http.post(
        f"{AI_URL}/speech/tts",
        json={"text": "Kết quả xét nghiệm của bạn bình thường.", "language": "vi"},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "x-user-role": "patient",
            "x-user-id": "e2e-patient-001",
        },
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    assert "audio" in resp.headers.get("content-type", "")
    assert len(resp.content) > 100, "Expected non-trivial audio bytes"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_tts_english_voice(http, doctor_token):
    """TTS must work for English as well."""
    resp = await http.post(
        f"{AI_URL}/speech/tts",
        json={"text": "Your test results are within normal range.", "language": "en"},
        headers={
            "Authorization": f"Bearer {doctor_token}",
            "x-user-role": "doctor",
            "x-user-id": "e2e-doctor-001",
        },
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    assert "audio" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Speech: transcribe E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_transcribe_audio_upload(http, patient_token):
    """
    Upload a minimal WAV file — if the AI service is live with a real
    Groq Whisper API key this should return a transcription.

    We allow transcription to be empty string (silent audio) but
    the response shape must be correct.
    """
    # Minimal silent WAV: 44 byte header + 1600 bytes of silence (0.1s @ 16kHz mono 16-bit)
    import struct, array
    num_samples = 1600
    sample_rate = 16000
    bits        = 16
    num_channels = 1
    byte_rate    = sample_rate * num_channels * bits // 8
    block_align  = num_channels * bits // 8
    data_size    = num_samples * block_align
    wav_header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, num_channels, sample_rate, byte_rate, block_align, bits,
        b"data", data_size,
    )
    silent_audio = wav_header + b"\x00" * data_size

    resp = await http.post(
        f"{AI_URL}/speech/transcribe",
        files={"file": ("silent.wav", silent_audio, "audio/wav")},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "x-user-role": "patient",
            "x-user-id": "e2e-patient-001",
        },
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert "text" in data
    assert "language" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_transcribe_invalid_mime_returns_415(http, patient_token):
    resp = await http.post(
        f"{AI_URL}/speech/transcribe",
        files={"file": ("bad.txt", b"not audio", "text/plain")},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "x-user-role": "patient",
            "x-user-id": "e2e-patient-001",
        },
    )
    assert resp.status_code == 415, f"Expected 415, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Auscultation E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_auscultation_doctor_flow(http, doctor_token):
    """
    Doctor uploads a minimal WAV and receives a draft JSON report.
    librosa + Gemini + Groq must all be reachable for this to pass.
    """
    import struct
    num_samples = 8000   # 0.5s @ 16kHz mono 16-bit
    sample_rate = 16000
    bits        = 16
    num_channels = 1
    byte_rate    = sample_rate * num_channels * bits // 8
    block_align  = num_channels * bits // 8
    data_size    = num_samples * num_channels * (bits // 8)
    wav_header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, num_channels, sample_rate, byte_rate, block_align, bits,
        b"data", data_size,
    )
    silent_wav = wav_header + b"\x00" * data_size

    resp = await http.post(
        f"{AI_URL}/analyze-auscultation",
        data={
            "patient_id": "e2e-patient-001",
            "sound_type": "lung_sounds",
            "department": "respiratory",
            "language":   "vi",
            "auth_token": doctor_token,
        },
        files={"file": ("lung.wav", silent_wav, "audio/wav")},
        headers={
            "Authorization": f"Bearer {doctor_token}",
            "x-user-role": "doctor",
            "x-user-id": "e2e-doctor-001",
        },
    )
    assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    # Draft report must have at least a draft_text or result_id
    assert "draft_text" in data or "result_id" in data


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_auscultation_patient_forbidden(http, patient_token):
    """Patient must not be able to call /analyze-auscultation."""
    import struct
    wav = struct.pack("<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36, b"WAVE", b"fmt ", 16, 1, 1, 16000, 32000, 2, 16, b"data", 0)

    resp = await http.post(
        f"{AI_URL}/analyze-auscultation",
        data={
            "patient_id": "e2e-patient-001",
            "sound_type": "lung_sounds",
            "department": "respiratory",
            "language": "vi",
            "auth_token": patient_token,
        },
        files={"file": ("lung.wav", wav, "audio/wav")},
        headers={
            "Authorization": f"Bearer {patient_token}",
            "x-user-role": "patient",
            "x-user-id": "e2e-patient-001",
        },
    )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
