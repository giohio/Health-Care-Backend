"""
Unit tests for Application/speech_synthesizer.py — SpeechSynthesizer.

edge-tts is mocked at the module level so no real TTS calls are made
(and the library does not need to be installed for tests to pass).
"""

import asyncio
import pytest
import sys
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fake edge_tts.Communicate streaming response
# ---------------------------------------------------------------------------

class FakeCommunicate:
    """Mimics the edge_tts.Communicate async stream interface."""

    def __init__(self, text: str, voice: str, chunks=None):
        self.text = text
        self.voice = voice
        self._chunks = chunks or [
            {"type": "audio", "data": b"\xff\xfb\x90"},
            {"type": "audio", "data": b"\x00\x00\x01"},
            {"type": "WordBoundary", "data": {}},           # non-audio chunk
        ]

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


def _make_fake_edge_tts(communicate_cls=None):
    module = MagicMock()
    module.Communicate = communicate_cls or FakeCommunicate
    return module


# ---------------------------------------------------------------------------
# Tests: basic synthesis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_returns_bytes_on_success():
    fake_edge_tts = _make_fake_edge_tts()

    with patch.dict(sys.modules, {"edge_tts": fake_edge_tts}):
        # Reload the module so the import runs with fake edge_tts
        import importlib
        import Application.speech_synthesizer as ss_mod
        importlib.reload(ss_mod)  # picks up the patched sys.modules
        ss_mod._EDGE_TTS_AVAILABLE = True  # force flag

        synth = ss_mod.SpeechSynthesizer()
        result = await synth.synthesize("Xét nghiệm bình thường.", language="vi")

    assert isinstance(result, bytes)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_synthesize_raises_runtime_error_when_not_installed():
    """If edge-tts is unavailable, synthesize() must raise RuntimeError."""
    import importlib
    import Application.speech_synthesizer as ss_mod
    importlib.reload(ss_mod)
    ss_mod._EDGE_TTS_AVAILABLE = False  # simulate missing package

    synth = ss_mod.SpeechSynthesizer()
    with pytest.raises(RuntimeError, match="edge-tts"):
        await synth.synthesize("Any text", language="vi")


@pytest.mark.asyncio
async def test_synthesize_concats_only_audio_chunks():
    """Only chunks with type='audio' must be written to the buffer."""
    audio_chunk_a = b"\xff\xfb\x10"
    audio_chunk_b = b"\xab\xcd"

    class FakeComm:
        def __init__(self, text, voice):
            pass

        async def stream(self):
            yield {"type": "audio", "data": audio_chunk_a}
            yield {"type": "WordBoundary", "data": {}}       # must be skipped
            yield {"type": "audio", "data": audio_chunk_b}

    fake_edge_tts = _make_fake_edge_tts(FakeComm)

    import importlib
    import Application.speech_synthesizer as ss_mod
    importlib.reload(ss_mod)
    ss_mod._EDGE_TTS_AVAILABLE = True
    ss_mod.edge_tts = fake_edge_tts

    synth = ss_mod.SpeechSynthesizer()
    result = await synth.synthesize("Hello", language="en")

    assert result == audio_chunk_a + audio_chunk_b


@pytest.mark.asyncio
async def test_synthesize_raises_when_audio_is_empty():
    """If edge-tts produces no audio bytes, RuntimeError must be raised."""

    class FakeCommEmpty:
        def __init__(self, text, voice):
            pass

        async def stream(self):
            yield {"type": "WordBoundary", "data": {}}   # no audio chunks at all

    fake_edge_tts = _make_fake_edge_tts(FakeCommEmpty)

    import importlib
    import Application.speech_synthesizer as ss_mod
    importlib.reload(ss_mod)
    ss_mod._EDGE_TTS_AVAILABLE = True
    ss_mod.edge_tts = fake_edge_tts

    synth = ss_mod.SpeechSynthesizer()
    with pytest.raises(RuntimeError):
        await synth.synthesize("Something", language="vi")


# ---------------------------------------------------------------------------
# Tests: voice selection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_vi_voice_is_hoai_my():
    received_voices = []

    class FakeCommRecorder:
        def __init__(self, text, voice):
            received_voices.append(voice)

        async def stream(self):
            yield {"type": "audio", "data": b"\x01"}

    fake_edge_tts = _make_fake_edge_tts(FakeCommRecorder)

    import importlib
    import Application.speech_synthesizer as ss_mod
    importlib.reload(ss_mod)
    ss_mod._EDGE_TTS_AVAILABLE = True
    ss_mod.edge_tts = fake_edge_tts

    synth = ss_mod.SpeechSynthesizer()
    await synth.synthesize("Xin chào", language="vi")

    assert received_voices[0] == "vi-VN-HoaiMyNeural"


@pytest.mark.asyncio
async def test_default_en_voice_is_jenny():
    received_voices = []

    class FakeCommRecorder:
        def __init__(self, text, voice):
            received_voices.append(voice)

        async def stream(self):
            yield {"type": "audio", "data": b"\x01"}

    fake_edge_tts = _make_fake_edge_tts(FakeCommRecorder)

    import importlib
    import Application.speech_synthesizer as ss_mod
    importlib.reload(ss_mod)
    ss_mod._EDGE_TTS_AVAILABLE = True
    ss_mod.edge_tts = fake_edge_tts

    synth = ss_mod.SpeechSynthesizer()
    await synth.synthesize("Hello", language="en")

    assert received_voices[0] == "en-US-JennyNeural"


@pytest.mark.asyncio
async def test_explicit_voice_overrides_language_default():
    received_voices = []

    class FakeCommRecorder:
        def __init__(self, text, voice):
            received_voices.append(voice)

        async def stream(self):
            yield {"type": "audio", "data": b"\x01"}

    fake_edge_tts = _make_fake_edge_tts(FakeCommRecorder)

    import importlib
    import Application.speech_synthesizer as ss_mod
    importlib.reload(ss_mod)
    ss_mod._EDGE_TTS_AVAILABLE = True
    ss_mod.edge_tts = fake_edge_tts

    synth = ss_mod.SpeechSynthesizer()
    await synth.synthesize("Xin chào", language="vi", voice="vi-VN-NamMinhNeural")

    assert received_voices[0] == "vi-VN-NamMinhNeural"


@pytest.mark.asyncio
async def test_unknown_language_falls_back_to_vi_voice():
    received_voices = []

    class FakeCommRecorder:
        def __init__(self, text, voice):
            received_voices.append(voice)

        async def stream(self):
            yield {"type": "audio", "data": b"\x01"}

    fake_edge_tts = _make_fake_edge_tts(FakeCommRecorder)

    import importlib
    import Application.speech_synthesizer as ss_mod
    importlib.reload(ss_mod)
    ss_mod._EDGE_TTS_AVAILABLE = True
    ss_mod.edge_tts = fake_edge_tts

    synth = ss_mod.SpeechSynthesizer()
    await synth.synthesize("Merhaba", language="tr")  # unknown language

    # Should fall back to vi (the dict .get default)
    assert received_voices[0] in ("vi-VN-HoaiMyNeural",)
