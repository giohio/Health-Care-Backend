from fastapi import APIRouter, UploadFile, File, Header, Depends, HTTPException
from fastapi.responses import Response
from presentation.schema import TtsInput, TranscriptionResponse
from Application.speech_transcriber import SpeechTranscriber
from Application.speech_synthesizer import SpeechSynthesizer
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/speech", tags=["AI - Speech"])

_ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/x-wav",
    "audio/mpeg", "audio/mp3",
    "audio/webm",
    "audio/mp4", "audio/m4a",
    "audio/ogg",
    "application/octet-stream",   # fallback for some clients
}

_MAX_AUDIO_BYTES = 25 * 1024 * 1024   # 25 MB — Groq Whisper limit


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file:        UploadFile = File(..., description="Audio file (wav/mp3/webm/m4a/ogg)"),
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
):
    """
    Speech-to-Text using Groq Whisper (`whisper-large-v3-turbo`).

    Accepts multipart audio upload.  Returns transcribed text and the detected
    language code (e.g. `"vi"`, `"en"`).

    Max file size: 25 MB.
    """
    if file.content_type not in _ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio format: {file.content_type}. "
                   "Accepted: wav, mp3, webm, m4a, ogg.",
        )

    audio_bytes = await file.read()
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Audio file exceeds the 25 MB limit.",
        )

    transcriber = SpeechTranscriber()
    result = await transcriber.transcribe(audio_bytes, filename=file.filename or "audio.wav")
    return TranscriptionResponse(text=result["text"], language=result["language"])


@router.post("/tts")
async def text_to_speech(
    body:        TtsInput,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
):
    """
    Text-to-Speech using Microsoft edge-tts (free, offline-capable).

    Default voices:
    - Vietnamese: `vi-VN-HoaiMyNeural`
    - English:    `en-US-JennyNeural`

    Returns an `audio/mpeg` (MP3) binary response.
    """
    synthesizer = SpeechSynthesizer()
    audio_bytes = await synthesizer.synthesize(
        text=body.text,
        language=body.language,
        voice=body.voice,
    )
    return Response(content=audio_bytes, media_type="audio/mpeg")
