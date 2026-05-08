"""
Auscultation audio analysis pipeline.

Flow:
  1. Receive WAV/MP3 audio of lung or heart sounds
  2. Convert to spectrogram image (PNG) in-memory
  3. Send spectrogram → Gemini Vision → structured findings JSON
  4. Fetch patient context from clinical_service
  5. Build synthesis prompt with findings + RAG guidelines context
  6. Send to Groq → stream clinical commentary

The spectrogram conversion turns audio into a 2D visual representation
(time × frequency mel-spectrogram) that Gemini Vision can analyse.
"""

import io
import logging
import base64
from typing import Optional
import numpy as np

from Domain.entities import LabAnalysisResult, PatientContext
from Domain.prompts import (
    AUSCULTATION_VISION_PROMPTS,
    AUSCULTATION_SYNTHESIS_SYSTEM,
    build_auscultation_synthesis_prompt,
)
from Domain.interfaces import ILLMClient, IVisionClient, IClinicalClient, IRetriever
from infrastructure.config import get_settings

logger = logging.getLogger(__name__)

try:
    import librosa
    import librosa.display
    import matplotlib
    matplotlib.use("Agg")   # non-interactive backend
    import matplotlib.pyplot as plt
    _LIBROSA_AVAILABLE = True
except ImportError:
    _LIBROSA_AVAILABLE = False
    logger.warning("librosa not installed — auscultation spectrogram disabled; "
                   "raw audio will be sent to Gemini instead.")


def _audio_to_spectrogram_png(audio_bytes: bytes) -> bytes:
    """
    Convert raw audio bytes to a mel-spectrogram PNG.
    Returns PNG bytes.
    Raises RuntimeError if librosa is not available.
    """
    if not _LIBROSA_AVAILABLE:
        raise RuntimeError(
            "librosa is required for spectrogram generation. "
            "Install it with: pip install librosa matplotlib"
        )

    audio_io = io.BytesIO(audio_bytes)
    y, sr = librosa.load(audio_io, sr=None, mono=True)

    mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=8000)
    mel_db = librosa.power_to_db(mel, ref=np.max)

    fig, ax = plt.subplots(figsize=(10, 4), dpi=100)
    librosa.display.specshow(mel_db, sr=sr, x_axis="time", y_axis="mel",
                             fmax=8000, ax=ax)
    ax.set_title("Mel Spectrogram")
    plt.colorbar(format="%+2.0f dB", ax=ax)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


class AuscultationAnalysisUseCase:
    """
    Tier 2: Auscultation audio analysis (lung sounds + heart sounds).

    Converts audio to mel-spectrogram → Gemini Vision extracts findings →
    Groq synthesizes clinical commentary with RAG guidelines context.
    """

    def __init__(
        self,
        llm:       ILLMClient,
        gemini:    IVisionClient,
        clinical:  IClinicalClient,
        retriever: Optional[IRetriever] = None,
    ) -> None:
        self._llm       = llm
        self._gemini    = gemini
        self._clinical  = clinical
        self._retriever = retriever

    async def execute(
        self,
        audio_bytes: bytes,
        patient_id:  str,
        sound_type:  str,     # "lung_sounds" | "heart_sounds"
        department:  str,     # "respiratory" | "cardiology"
        language:    str,     # "vi" | "en"
        x_user_id:   str,
        x_user_role: str,
    ) -> LabAnalysisResult:
        settings = get_settings()

        # Step 1: patient context
        context = await self._clinical.get_patient_context(
            patient_id, x_user_id, x_user_role
        )

        # Step 2: generate spectrogram and extract findings via Gemini
        vision_prompt_key = sound_type
        try:
            png_bytes = _audio_to_spectrogram_png(audio_bytes)
            findings  = await self._gemini.extract_findings(
                png_bytes, "image/png", vision_prompt_key
            )
        except RuntimeError as exc:
            # librosa not available — send raw audio bytes as base64 image fallback
            logger.warning("Spectrogram unavailable: %s. Falling back.", exc)
            findings = {"error": str(exc), "keywords": [], "confidence": 0.0}

        if findings.get("error"):
            return LabAnalysisResult(
                result_id="auscultation",
                visual_findings=None,
                draft_text="⚠️ Unable to analyze audio. Manual check required.",
                confidence=0.0,
                citations=[],
                model_versions={
                    "vision": settings.GEMINI_VISION_MODEL,
                    "text":   settings.GROQ_TEXT_MODEL,
                },
            )

        # Step 3: RAG — retrieve relevant guidelines for the department
        rag_context = ""
        if self._retriever:
            keywords    = " ".join(findings.get("keywords", [])[:5])
            rag_context = await self._retriever.get_context(
                keywords or sound_type.replace("_", " "),
                department=department,
                top_k=3,
            )

        # Step 4: synthesize draft with Groq
        user_prompt = build_auscultation_synthesis_prompt(
            findings, context, sound_type, language=language
        )
        if rag_context:
            user_prompt = f"{rag_context}\n\n{user_prompt}"

        draft_text = await self._llm.complete(
            system_prompt=AUSCULTATION_SYNTHESIS_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=2048,
        )

        return LabAnalysisResult(
            result_id="auscultation",
            visual_findings=findings,
            draft_text=draft_text,
            confidence=float(findings.get("confidence", 0.6)),
            citations=[],
            model_versions={
                "vision": settings.GEMINI_VISION_MODEL,
                "text":   settings.GROQ_TEXT_MODEL,
            },
        )

