"""
Text-to-Speech via edge-tts (Microsoft Azure Neural TTS, free, no API key).

Supported Vietnamese voice: vi-VN-HoaiMyNeural (female, natural)
Supported English voice:    en-US-JennyNeural   (female, natural)

edge-tts streams audio directly; we collect it all and return as bytes.
"""

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False
    logger.warning("edge-tts not installed — TTS unavailable. "
                   "Install with: pip install edge-tts")

_DEFAULT_VOICES = {
    "vi": "vi-VN-HoaiMyNeural",
    "en": "en-US-JennyNeural",
}


class SpeechSynthesizer:
    async def synthesize(
        self,
        text:     str,
        language: str = "en",
        voice:    Optional[str] = None,
    ) -> bytes:
        """
        Convert text to speech and return raw MP3 bytes.
        """
        if not _EDGE_TTS_AVAILABLE:
            raise RuntimeError(
                "edge-tts is not installed. Run: pip install edge-tts"
            )

        selected_voice = voice or _DEFAULT_VOICES.get(language, _DEFAULT_VOICES["vi"])

        communicate = edge_tts.Communicate(text=text, voice=selected_voice)

        audio_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])

        audio_bytes = audio_buffer.getvalue()
        if not audio_bytes:
            raise RuntimeError(f"edge-tts returned empty audio for voice={selected_voice}")

        return audio_bytes

