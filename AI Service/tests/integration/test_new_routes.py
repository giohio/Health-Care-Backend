"""
Integration tests for new AI Service HTTP routes:
  POST /lab-chat
  POST /clinical-assist
  POST /speech/transcribe
  POST /speech/tts
  POST /analyze-auscultation

All use cases / external clients are replaced via dependency overrides or
monkeypatching.  No real LLM / Whisper / edge-tts / Groq calls are made.
"""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from Domain.entities import LabAnalysisResult
from presentation.dependencies import (
    get_lab_chat_usecase,
    get_clinical_assist_usecase,
)


# ---------------------------------------------------------------------------
# Fake use cases
# ---------------------------------------------------------------------------

class FakeLabChatUseCase:
    async def execute(self, question, x_user_id, x_user_role, patient_id=None, department=None):
        yield "Lab interpretation: "
        yield "HbA1c 9.2% suggests poor glycaemic control."
        if x_user_role not in ("doctor", "admin"):
            yield " ⚠️ AI disclaimer"


class FakeClinicalAssistUseCase:
    async def execute(self, question, x_user_id, x_user_role, patient_id=None, department=None):
        yield "Clinical assessment: "
        yield "Differential includes T2DM, MODY."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def override_new_dependencies(app):
    """Inject fake new use cases for every test in this module."""
    app.dependency_overrides[get_lab_chat_usecase] = lambda: FakeLabChatUseCase()
    app.dependency_overrides[get_clinical_assist_usecase] = lambda: FakeClinicalAssistUseCase()
    yield
    # Remove only our additions (existing overrides stay via the outer autouse fixture)
    app.dependency_overrides.pop(get_lab_chat_usecase, None)
    app.dependency_overrides.pop(get_clinical_assist_usecase, None)


# ---------------------------------------------------------------------------
# POST /lab-chat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lab_chat_returns_sse_stream(client):
    resp = await client.post(
        "/lab-chat",
        json={"question": "What does HbA1c 9.2% mean?"},
        headers={"x-user-id": "u-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "data: " in body
    assert "data: [DONE]" in body


@pytest.mark.asyncio
async def test_lab_chat_contains_use_case_output(client):
    resp = await client.post(
        "/lab-chat",
        json={"question": "HbA1c interpretation"},
        headers={"x-user-id": "u-001", "x-user-role": "doctor"},
    )
    body = resp.text
    assert "HbA1c 9.2%" in body or "interpretation" in body.lower() or "Lab" in body


@pytest.mark.asyncio
async def test_lab_chat_missing_headers_returns_422(client):
    resp = await client.post(
        "/lab-chat",
        json={"question": "What is WBC?"},
        # Missing x-user-id / x-user-role
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_lab_chat_missing_question_returns_422(client):
    resp = await client.post(
        "/lab-chat",
        json={},  # question is required
        headers={"x-user-id": "u-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_lab_chat_with_patient_id_and_department(client):
    """Optional fields should be accepted without error."""
    resp = await client.post(
        "/lab-chat",
        json={
            "question": "Explain my WBC result",
            "patient_id": "p-001",
            "department": "hematology",
        },
        headers={"x-user-id": "u-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /clinical-assist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clinical_assist_doctor_role_returns_200(client):
    resp = await client.post(
        "/clinical-assist",
        json={"question": "Differential for elevated troponin?"},
        headers={"x-user-id": "doc-001", "x-user-role": "doctor"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "data: [DONE]" in body


@pytest.mark.asyncio
async def test_clinical_assist_admin_role_allowed(client):
    resp = await client.post(
        "/clinical-assist",
        json={"question": "Review CKD staging"},
        headers={"x-user-id": "admin-001", "x-user-role": "admin"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_clinical_assist_patient_role_returns_403(client):
    resp = await client.post(
        "/clinical-assist",
        json={"question": "Tell me my diagnosis"},
        headers={"x-user-id": "p-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_clinical_assist_missing_headers_returns_422(client):
    resp = await client.post(
        "/clinical-assist",
        json={"question": "Any clinical question"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_clinical_assist_contains_use_case_output(client):
    resp = await client.post(
        "/clinical-assist",
        json={"question": "T2DM differentials"},
        headers={"x-user-id": "doc-001", "x-user-role": "doctor"},
    )
    body = resp.text
    assert "Clinical" in body or "Differential" in body or "T2DM" in body


# ---------------------------------------------------------------------------
# POST /speech/transcribe
# ---------------------------------------------------------------------------

def _wav_bytes() -> bytes:
    """Minimal valid-looking WAV header (content doesn't matter for unit tests)."""
    return b"RIFF" + b"\x00" * 40


@pytest.mark.asyncio
async def test_transcribe_returns_200_with_text_and_language(client):
    """SpeechTranscriber is monkeypatched so no real Groq Whisper call is made."""
    fake_result = {"text": "Bệnh nhân ho khan.", "language": "vi"}

    with patch(
        "presentation.routes.speech.SpeechTranscriber.transcribe",
        new=AsyncMock(return_value=fake_result),
    ):
        resp = await client.post(
            "/speech/transcribe",
            files={"file": ("test.wav", _wav_bytes(), "audio/wav")},
            headers={"x-user-id": "u-001", "x-user-role": "patient"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Bệnh nhân ho khan."
    assert data["language"] == "vi"


@pytest.mark.asyncio
async def test_transcribe_unsupported_mime_returns_415(client):
    resp = await client.post(
        "/speech/transcribe",
        files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        headers={"x-user-id": "u-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_transcribe_missing_headers_returns_422(client):
    resp = await client.post(
        "/speech/transcribe",
        files={"file": ("test.wav", _wav_bytes(), "audio/wav")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_transcribe_too_large_returns_413(client):
    # 26 MB — Groq limit is 25 MB
    big_audio = b"\x00" * (26 * 1024 * 1024)

    with patch(
        "presentation.routes.speech.SpeechTranscriber.transcribe",
        new=AsyncMock(return_value={"text": "", "language": "vi"}),
    ):
        resp = await client.post(
            "/speech/transcribe",
            files={"file": ("big.wav", big_audio, "audio/wav")},
            headers={"x-user-id": "u-001", "x-user-role": "patient"},
        )

    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# POST /speech/tts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tts_returns_200_audio_mpeg(client):
    fake_audio = b"\xff\xfb\x90" + b"\x00" * 50  # MP3-like bytes

    with patch(
        "presentation.routes.speech.SpeechSynthesizer.synthesize",
        new=AsyncMock(return_value=fake_audio),
    ):
        resp = await client.post(
            "/speech/tts",
            json={"text": "Xét nghiệm bình thường.", "language": "vi"},
            headers={"x-user-id": "u-001", "x-user-role": "patient"},
        )

    assert resp.status_code == 200
    assert "audio/mpeg" in resp.headers["content-type"]
    assert resp.content == fake_audio


@pytest.mark.asyncio
async def test_tts_missing_text_returns_422(client):
    resp = await client.post(
        "/speech/tts",
        json={"language": "vi"},
        headers={"x-user-id": "u-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tts_missing_headers_returns_422(client):
    resp = await client.post(
        "/speech/tts",
        json={"text": "Hello", "language": "en"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_tts_with_explicit_voice(client):
    fake_audio = b"\xff\xfb\x90"

    with patch(
        "presentation.routes.speech.SpeechSynthesizer.synthesize",
        new=AsyncMock(return_value=fake_audio),
    ) as mock_synthesize:
        await client.post(
            "/speech/tts",
            json={"text": "Test", "language": "vi", "voice": "vi-VN-NamMinhNeural"},
            headers={"x-user-id": "u-001", "x-user-role": "doctor"},
        )

    mock_synthesize.assert_called_once()
    _, kwargs = mock_synthesize.call_args
    assert kwargs.get("voice") == "vi-VN-NamMinhNeural"


# ---------------------------------------------------------------------------
# POST /analyze-auscultation
# ---------------------------------------------------------------------------

def _fake_auscultation_result() -> LabAnalysisResult:
    return LabAnalysisResult(
        result_id="auscultation",
        visual_findings={"findings": "Bilateral crackles.", "keywords": ["crackles"]},
        draft_text="Bilateral crackles suggest pulmonary oedema.",
        confidence=0.80,
        citations=[],
        model_versions={"vision": "gemini-v", "text": "llama3"},
    )


@pytest.mark.asyncio
async def test_analyze_auscultation_doctor_returns_200(client):
    with patch(
        "presentation.routes.auscultation.AuscultationAnalysisUseCase.execute",
        new=AsyncMock(return_value=_fake_auscultation_result()),
    ) as mock_execute:
        resp = await client.post(
            "/analyze-auscultation",
            data={
                "patient_id": "p-001",
                "sound_type": "lung_sounds",
                "department": "respiratory",
                "language": "vi",
                "auth_token": "tok-test",
            },
            files={"file": ("heart.wav", _wav_bytes(), "audio/wav")},
            headers={"x-user-id": "doc-001", "x-user-role": "doctor"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["patient_id"] == "p-001"
    assert data["sound_type"] == "lung_sounds"
    assert data["department"] == "respiratory"
    assert data["visual_findings"]["findings"] == "Bilateral crackles."
    assert data["draft_text"] == "Bilateral crackles suggest pulmonary oedema."
    assert data["confidence"] == 0.80
    assert data["model_versions"] == {"vision": "gemini-v", "text": "llama3"}
    mock_execute.assert_awaited_once_with(
        audio_bytes=_wav_bytes(),
        patient_id="p-001",
        sound_type="lung_sounds",
        department="respiratory",
        language="vi",
        x_user_id="doc-001",
        x_user_role="doctor",
    )


@pytest.mark.asyncio
async def test_analyze_auscultation_heart_sound_webm_returns_200(client):
    with patch(
        "presentation.routes.auscultation.AuscultationAnalysisUseCase.execute",
        new=AsyncMock(return_value=_fake_auscultation_result()),
    ) as mock_execute:
        resp = await client.post(
            "/analyze-auscultation",
            data={
                "patient_id": "p-002",
                "sound_type": "heart_sounds",
                "department": "cardiology",
                "language": "en",
                "auth_token": "tok-test",
            },
            files={"file": ("heart.webm", b"webm-audio", "audio/webm")},
            headers={"x-user-id": "doc-002", "x-user-role": "doctor"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["sound_type"] == "heart_sounds"
    assert data["department"] == "cardiology"
    mock_execute.assert_awaited_once_with(
        audio_bytes=b"webm-audio",
        patient_id="p-002",
        sound_type="heart_sounds",
        department="cardiology",
        language="en",
        x_user_id="doc-002",
        x_user_role="doctor",
    )


@pytest.mark.asyncio
async def test_analyze_auscultation_patient_returns_403(client):
    resp = await client.post(
        "/analyze-auscultation",
        data={
            "patient_id": "p-001",
            "sound_type": "lung_sounds",
            "department": "respiratory",
            "language": "vi",
            "auth_token": "tok",
        },
        files={"file": ("audio.wav", _wav_bytes(), "audio/wav")},
        headers={"x-user-id": "p-001", "x-user-role": "patient"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_analyze_auscultation_invalid_sound_type_returns_422(client):
    resp = await client.post(
        "/analyze-auscultation",
        data={
            "patient_id": "p-001",
            "sound_type": "kidney_sounds",     # invalid
            "department": "respiratory",
            "language": "vi",
            "auth_token": "tok",
        },
        files={"file": ("audio.wav", _wav_bytes(), "audio/wav")},
        headers={"x-user-id": "doc-001", "x-user-role": "doctor"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analyze_auscultation_invalid_department_returns_422(client):
    resp = await client.post(
        "/analyze-auscultation",
        data={
            "patient_id": "p-001",
            "sound_type": "lung_sounds",
            "department": "ophthalmology",    # invalid for auscultation
            "language": "vi",
            "auth_token": "tok",
        },
        files={"file": ("audio.wav", _wav_bytes(), "audio/wav")},
        headers={"x-user-id": "doc-001", "x-user-role": "doctor"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analyze_auscultation_unsupported_mime_returns_415(client):
    resp = await client.post(
        "/analyze-auscultation",
        data={
            "patient_id": "p-001",
            "sound_type": "heart_sounds",
            "department": "cardiology",
            "language": "en",
            "auth_token": "tok",
        },
        files={"file": ("image.txt", b"not audio", "text/plain")},
        headers={"x-user-id": "doc-001", "x-user-role": "doctor"},
    )
    assert resp.status_code == 415
