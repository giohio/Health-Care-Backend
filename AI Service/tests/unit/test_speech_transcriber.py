"""
Unit tests for Application/speech_transcriber.py — SpeechTranscriber.

The Groq AsyncClient is mocked at the class level so no real network calls
are made. The test Fake mimics the `verbose_json` response shape.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Fake Groq Whisper response
# ---------------------------------------------------------------------------

class FakeTranscription:
    def __init__(self, text: str, language: str = "vi"):
        self.text = text
        self.language = language


class FakeTranscriptions:
    def __init__(self, text: str = "Xét nghiệm máu bình thường.", language: str = "vi"):
        self._text = text
        self._language = language
        self.last_call_kwargs: dict = {}

    async def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        await asyncio.sleep(0)
        return FakeTranscription(text=self._text, language=self._language)


class FakeAudio:
    def __init__(self, text: str = "Xét nghiệm máu bình thường.", language: str = "vi"):
        self.transcriptions = FakeTranscriptions(text=text, language=language)


class FakeAsyncGroq:
    def __init__(self, text="Xét nghiệm máu bình thường.", language="vi", api_key=None):
        self.audio = FakeAudio(text=text, language=language)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transcribe_returns_text_and_language():
    with patch("Application.speech_transcriber.AsyncGroq") as mock_groq_cls, \
         patch("Application.speech_transcriber.get_settings") as mock_settings:

        mock_settings.return_value = MagicMock(GROQ_API_KEY="fake-key")
        fake_groq = FakeAsyncGroq(text="Bệnh nhân ho khan.", language="vi")
        mock_groq_cls.return_value = fake_groq

        from Application.speech_transcriber import SpeechTranscriber
        transcriber = SpeechTranscriber()
        result = await transcriber.transcribe(b"fake-audio-bytes")

    assert result["text"] == "Bệnh nhân ho khan."
    assert result["language"] == "vi"


@pytest.mark.asyncio
async def test_transcribe_strips_whitespace():
    with patch("Application.speech_transcriber.AsyncGroq") as mock_groq_cls, \
         patch("Application.speech_transcriber.get_settings") as mock_settings:

        mock_settings.return_value = MagicMock(GROQ_API_KEY="fake-key")
        fake_groq = FakeAsyncGroq(text="  Patient has fever.  ", language="en")
        mock_groq_cls.return_value = fake_groq

        from Application.speech_transcriber import SpeechTranscriber
        transcriber = SpeechTranscriber()
        result = await transcriber.transcribe(b"bytes")

    assert result["text"] == "Patient has fever."


@pytest.mark.asyncio
async def test_transcribe_passes_filename_and_bytes_to_api():
    with patch("Application.speech_transcriber.AsyncGroq") as mock_groq_cls, \
         patch("Application.speech_transcriber.get_settings") as mock_settings:

        mock_settings.return_value = MagicMock(GROQ_API_KEY="fake-key")
        fake_groq = FakeAsyncGroq()
        mock_groq_cls.return_value = fake_groq

        from Application.speech_transcriber import SpeechTranscriber
        transcriber = SpeechTranscriber()
        audio_data = b"\x00\x01\x02"
        await transcriber.transcribe(audio_data, filename="recording.mp3")

    kwargs = fake_groq.audio.transcriptions.last_call_kwargs
    assert kwargs["file"] == ("recording.mp3", audio_data)


@pytest.mark.asyncio
async def test_transcribe_uses_whisper_model():
    with patch("Application.speech_transcriber.AsyncGroq") as mock_groq_cls, \
         patch("Application.speech_transcriber.get_settings") as mock_settings:

        mock_settings.return_value = MagicMock(GROQ_API_KEY="fake-key")
        fake_groq = FakeAsyncGroq()
        mock_groq_cls.return_value = fake_groq

        from Application.speech_transcriber import SpeechTranscriber
        transcriber = SpeechTranscriber()
        await transcriber.transcribe(b"bytes")

    kwargs = fake_groq.audio.transcriptions.last_call_kwargs
    assert "whisper" in kwargs.get("model", "").lower()


@pytest.mark.asyncio
async def test_transcribe_requests_verbose_json_format():
    with patch("Application.speech_transcriber.AsyncGroq") as mock_groq_cls, \
         patch("Application.speech_transcriber.get_settings") as mock_settings:

        mock_settings.return_value = MagicMock(GROQ_API_KEY="fake-key")
        fake_groq = FakeAsyncGroq()
        mock_groq_cls.return_value = fake_groq

        from Application.speech_transcriber import SpeechTranscriber
        transcriber = SpeechTranscriber()
        await transcriber.transcribe(b"bytes")

    kwargs = fake_groq.audio.transcriptions.last_call_kwargs
    assert kwargs.get("response_format") == "verbose_json"


@pytest.mark.asyncio
async def test_transcribe_default_filename_is_wav():
    with patch("Application.speech_transcriber.AsyncGroq") as mock_groq_cls, \
         patch("Application.speech_transcriber.get_settings") as mock_settings:

        mock_settings.return_value = MagicMock(GROQ_API_KEY="fake-key")
        fake_groq = FakeAsyncGroq()
        mock_groq_cls.return_value = fake_groq

        from Application.speech_transcriber import SpeechTranscriber
        transcriber = SpeechTranscriber()
        await transcriber.transcribe(b"bytes")

    kwargs = fake_groq.audio.transcriptions.last_call_kwargs
    filename, _ = kwargs["file"]
    assert filename.endswith(".wav")


@pytest.mark.asyncio
async def test_transcribe_english_audio():
    with patch("Application.speech_transcriber.AsyncGroq") as mock_groq_cls, \
         patch("Application.speech_transcriber.get_settings") as mock_settings:

        mock_settings.return_value = MagicMock(GROQ_API_KEY="fake-key")
        fake_groq = FakeAsyncGroq(text="The patient has elevated troponin.", language="en")
        mock_groq_cls.return_value = fake_groq

        from Application.speech_transcriber import SpeechTranscriber
        transcriber = SpeechTranscriber()
        result = await transcriber.transcribe(b"english-audio")

    assert result["text"] == "The patient has elevated troponin."
    assert result["language"] == "en"


@pytest.mark.asyncio
async def test_transcribe_uses_groq_api_key_from_settings():
    """Ensure the AsyncGroq client is initialized with the API key from settings."""
    with patch("Application.speech_transcriber.AsyncGroq") as mock_groq_cls, \
         patch("Application.speech_transcriber.get_settings") as mock_settings:

        mock_settings.return_value = MagicMock(GROQ_API_KEY="my-secret-key-xyz")
        fake_groq = FakeAsyncGroq()
        mock_groq_cls.return_value = fake_groq

        from Application.speech_transcriber import SpeechTranscriber
        SpeechTranscriber()

    mock_groq_cls.assert_called_once_with(api_key="my-secret-key-xyz")
