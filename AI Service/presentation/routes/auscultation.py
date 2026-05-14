from fastapi import APIRouter, Depends, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import JSONResponse
from Application.auscultation_analysis import AuscultationAnalysisUseCase
from presentation.dependencies import get_auscultation_usecase
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyze-auscultation", tags=["AI - Auscultation"])

_ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/x-wav",
    "audio/mpeg", "audio/mp3",
    "audio/webm",
    "audio/mp4", "audio/m4a",
    "audio/ogg",
    "application/octet-stream",
}

_MAX_AUDIO_BYTES = 25 * 1024 * 1024   # 25 MB

_DOCTOR_ROLES = {"doctor", "admin"}


@router.post("")
async def analyze_auscultation(
    file:        UploadFile = File(..., description="Audio recording (wav/mp3/ogg)"),
    patient_id:  str  = Form(...),
    sound_type:  str  = Form(..., description="lung_sounds | heart_sounds"),
    department:  str  = Form(..., description="respiratory | cardiology"),
    language:    str  = Form(default="vi", description="vi | en"),
    auth_token:  str  = Form(...),
    x_user_id:   str  = Header(...),
    x_user_role: str  = Header(...),
    use_case:    AuscultationAnalysisUseCase = Depends(get_auscultation_usecase),
):
    """
    Auscultation audio analysis — lung sounds or heart sounds.

    **Flow**: Upload audio → mel-spectrogram → Gemini Vision extract findings
    → Groq synthesis with RAG clinical guidelines → JSON draft report.

    - `sound_type`: `lung_sounds` (wheeze, crackles, rhonchi) or `heart_sounds` (murmurs, S3/S4)
    - `department`: `respiratory` or `cardiology`
    - Restricted to doctor / admin roles.
    - Returns a draft JSON report for physician review.
    """
    if x_user_role not in _DOCTOR_ROLES:
        raise HTTPException(status_code=403, detail="Auscultation analysis is for doctors only.")

    if sound_type not in ("lung_sounds", "heart_sounds"):
        raise HTTPException(status_code=422, detail="sound_type must be 'lung_sounds' or 'heart_sounds'.")

    if department not in ("respiratory", "cardiology"):
        raise HTTPException(status_code=422, detail="department must be 'respiratory' or 'cardiology'.")

    if file.content_type not in _ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio format: {file.content_type}.",
        )

    audio_bytes = await file.read()
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25 MB limit.")

    result = await use_case.execute(
        audio_bytes=audio_bytes,
        patient_id=patient_id,
        sound_type=sound_type,
        department=department,
        language=language,
        x_user_id=x_user_id,
        x_user_role=x_user_role,
    )

    return JSONResponse({
        "patient_id":       patient_id,
        "sound_type":       sound_type,
        "department":       department,
        "visual_findings": result.visual_findings,
        "draft_text":      result.draft_text,
        "confidence":      result.confidence,
        "model_versions":  result.model_versions,
        "requires_specialist_review": result.requires_specialist_review,
        "note":            "AI draft — requires physician review and approval.",
    })
