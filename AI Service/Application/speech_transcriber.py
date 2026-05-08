"""
Speech-to-Text via Groq Whisper API.

Groq provides transcription via the same API key already in use.
Model: whisper-large-v3-turbo  (fast, accurate, supports Vietnamese)
"""

import logging
from groq import AsyncGroq
from infrastructure.config import get_settings

logger = logging.getLogger(__name__)

_WHISPER_MODEL = "whisper-large-v3-turbo"


class SpeechTranscriber:
    def __init__(self) -> None:
        s = get_settings()
        self._client = AsyncGroq(api_key=s.GROQ_API_KEY)

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> dict:
        """
        Transcribe audio bytes using Groq Whisper.

        Args:
            audio_bytes: Raw audio file content (wav/mp3/webm/m4a/ogg).
            filename:    Original filename — used for MIME type inference.

        Returns:
            {"text": "...", "language": "vi"|"en"|...}
        """
        transcription = await self._client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=_WHISPER_MODEL,
            response_format="verbose_json",
        )

        return {
            "text":     transcription.text.strip(),
            "language": getattr(transcription, "language", "unknown"),
        }

