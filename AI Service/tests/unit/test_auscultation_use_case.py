"""
Unit tests for Application/auscultation_analysis.py — AuscultationAnalysisUseCase.

External I/O (Groq, Gemini, ClinicalClient, librosa, QdrantRetriever) is
replaced with Fake objects.  No real network or audio processing occurs.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock

from Domain.entities import PatientContext, LabAnalysisResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _yield_control():
    await asyncio.sleep(0)


FAKE_AUDIO_BYTES = b"\x52\x49\x46\x46" + b"\x00" * 44  # minimal WAV-like header


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeGroqClient:
    def __init__(self, response_text="Clinical interpretation of lung sounds."):
        self.last_system_prompt = None
        self.last_user_prompt = None
        self._text = response_text

    async def complete(self, system_prompt, user_prompt, **kwargs):
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        await _yield_control()
        return self._text


class FakeGeminiClient:
    def __init__(self, findings=None, fail=False):
        self.call_count = 0
        self.last_image_bytes = None
        self.last_prompt_key = None
        self._findings = findings or {
            "confidence": 0.82,
            "keywords": ["crackles", "reduced breath sounds"],
            "findings": "Bilateral crackles, reduced breath sounds at bases.",
        }
        self._fail = fail

    async def extract_findings(self, image_bytes, mime_type, prompt_key, **kwargs):
        self.call_count += 1
        self.last_image_bytes = image_bytes
        self.last_prompt_key = prompt_key
        await _yield_control()
        if self._fail:
            return {"error": "gemini_failed", "keywords": [], "confidence": 0.0}
        return self._findings


class FakeClinicalClient:
    def __init__(self, context=None):
        self.call_count = 0
        self._context = context or PatientContext(
            patient_id="p-asc",
            full_name="Test Auscultation Patient",
            age=65,
            gender="male",
            active_diagnoses=["COPD"],
        )

    async def get_patient_context(self, patient_id, x_user_id, x_user_role):
        self.call_count += 1
        await _yield_control()
        return self._context


class FakeRetriever:
    def __init__(self, context_text="Pulmonary guidelines text"):
        self.call_count = 0
        self.last_query = None
        self.last_department = None
        self._context = context_text

    async def get_context(self, query, department=None, top_k=3):
        self.call_count += 1
        self.last_query = query
        self.last_department = department
        await _yield_control()
        return self._context


# ---------------------------------------------------------------------------
# Helper: build use case with fake spectrogram
# ---------------------------------------------------------------------------

def _fake_spectrogram(audio_bytes: bytes) -> bytes:
    """Return fake PNG bytes without running librosa."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


# ---------------------------------------------------------------------------
# Tests: happy path — lung sounds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lung_sounds_pipeline_returns_result():
    groq = FakeGroqClient("Crackles suggest fluid in alveoli.")
    gemini = FakeGeminiClient()
    clinical = FakeClinicalClient()

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        side_effect=_fake_spectrogram,
    ):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(llm=groq, gemini=gemini, clinical=clinical)

        result = await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="lung_sounds",
            department="respiratory",
            language="vi",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    assert isinstance(result, LabAnalysisResult)
    assert result.result_id == "auscultation"
    assert result.draft_text == "Crackles suggest fluid in alveoli."
    assert result.confidence == pytest.approx(0.82)


@pytest.mark.asyncio
async def test_heart_sounds_uses_heart_sounds_prompt_key():
    groq = FakeGroqClient()
    gemini = FakeGeminiClient(findings={"confidence": 0.75, "keywords": ["S3 gallop"], "findings": "S3 gallop present."})
    clinical = FakeClinicalClient()

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        side_effect=_fake_spectrogram,
    ):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(llm=groq, gemini=gemini, clinical=clinical)

        await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="heart_sounds",
            department="cardiology",
            language="en",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    assert gemini.last_prompt_key == "heart_sounds"


@pytest.mark.asyncio
async def test_gemini_called_with_png_bytes():
    groq = FakeGroqClient()
    gemini = FakeGeminiClient()
    clinical = FakeClinicalClient()

    png_bytes = b"\x89PNG\r\n\x1a\nFAKEPNG"

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        return_value=png_bytes,
    ):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(llm=groq, gemini=gemini, clinical=clinical)

        await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="lung_sounds",
            department="respiratory",
            language="vi",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    assert gemini.last_image_bytes == png_bytes


@pytest.mark.asyncio
async def test_patient_context_is_fetched():
    groq = FakeGroqClient()
    gemini = FakeGeminiClient()
    clinical = FakeClinicalClient()

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        side_effect=_fake_spectrogram,
    ):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(llm=groq, gemini=gemini, clinical=clinical)

        await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="lung_sounds",
            department="respiratory",
            language="vi",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    assert clinical.call_count == 1


# ---------------------------------------------------------------------------
# Tests: Gemini failure — returns manual review draft
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_gemini_returns_manual_review_result():
    groq = FakeGroqClient()
    gemini = FakeGeminiClient(fail=True)
    clinical = FakeClinicalClient()

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        side_effect=_fake_spectrogram,
    ):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(llm=groq, gemini=gemini, clinical=clinical)

        result = await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="lung_sounds",
            department="respiratory",
            language="vi",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    # Use case must not call Groq if Gemini failed
    assert groq.last_user_prompt is None
    assert result.confidence == 0.0
    assert "kiểm tra thủ công" in result.draft_text or "manual" in result.draft_text.lower()


# ---------------------------------------------------------------------------
# Tests: spectrogram failure — fallback without findings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spectrogram_error_is_handled_gracefully():
    """If _audio_to_spectrogram_png raises RuntimeError (librosa missing),
    the pipeline should catch it and return a manual-review result."""
    groq = FakeGroqClient()
    gemini = FakeGeminiClient()
    clinical = FakeClinicalClient()

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        side_effect=RuntimeError("librosa not installed"),
    ):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(llm=groq, gemini=gemini, clinical=clinical)

        result = await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="lung_sounds",
            department="respiratory",
            language="vi",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    assert result.confidence == 0.0
    assert result.visual_findings is None


# ---------------------------------------------------------------------------
# Tests: RAG integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rag_not_called_when_no_retriever():
    groq = FakeGroqClient()
    gemini = FakeGeminiClient()
    clinical = FakeClinicalClient()

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        side_effect=_fake_spectrogram,
    ):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(
            llm=groq, gemini=gemini, clinical=clinical, retriever=None
        )

        result = await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="lung_sounds",
            department="respiratory",
            language="vi",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    assert isinstance(result, LabAnalysisResult)  # no crash when retriever=None


@pytest.mark.asyncio
async def test_rag_queried_with_keywords_and_department():
    groq = FakeGroqClient()
    gemini = FakeGeminiClient(findings={
        "confidence": 0.80,
        "keywords": ["crackles", "wheezing", "reduced"],
        "findings": "Crackles and wheezing.",
    })
    clinical = FakeClinicalClient()
    retriever = FakeRetriever("Respiratory KB guideline text")

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        side_effect=_fake_spectrogram,
    ):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(
            llm=groq, gemini=gemini, clinical=clinical, retriever=retriever
        )

        await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="lung_sounds",
            department="respiratory",
            language="vi",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    assert retriever.call_count == 1
    assert retriever.last_department == "respiratory"
    # First 5 keywords joined
    assert "crackles" in retriever.last_query


@pytest.mark.asyncio
async def test_rag_context_prepended_to_user_prompt():
    groq = FakeGroqClient()
    gemini = FakeGeminiClient(findings={
        "confidence": 0.70,
        "keywords": ["rhonchi"],
        "findings": "Rhonchi present.",
    })
    clinical = FakeClinicalClient()
    retriever = FakeRetriever("── KNOWLEDGE BASE CONTEXT ──\nCOPD guidelines\n── END CONTEXT ──")

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        side_effect=_fake_spectrogram,
    ):
        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(
            llm=groq, gemini=gemini, clinical=clinical, retriever=retriever
        )

        await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="lung_sounds",
            department="respiratory",
            language="vi",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    assert "KNOWLEDGE BASE CONTEXT" in groq.last_user_prompt
    assert "COPD guidelines" in groq.last_user_prompt


# ---------------------------------------------------------------------------
# Tests: result structure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_result_contains_model_versions():
    groq = FakeGroqClient()
    gemini = FakeGeminiClient()
    clinical = FakeClinicalClient()

    with patch(
        "Application.auscultation_analysis._audio_to_spectrogram_png",
        side_effect=_fake_spectrogram,
    ), patch("Application.auscultation_analysis.get_settings") as mock_settings:

        mock_settings.return_value = type("S", (), {
            "GEMINI_VISION_MODEL": "gemini-test-vision",
            "GROQ_TEXT_MODEL":    "llama3-test",
        })()

        from Application.auscultation_analysis import AuscultationAnalysisUseCase
        uc = AuscultationAnalysisUseCase(llm=groq, gemini=gemini, clinical=clinical)

        result = await uc.execute(
            audio_bytes=FAKE_AUDIO_BYTES,
            patient_id="p-asc",
            sound_type="heart_sounds",
            department="cardiology",
            language="en",
            x_user_id="doc-1",
            x_user_role="doctor",
        )

    assert result.model_versions["vision"] == "gemini-test-vision"
    assert result.model_versions["text"] == "llama3-test"



