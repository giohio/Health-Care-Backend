import re
import httpx
from typing import Optional
from Domain.entities import LabAnalysisRequest, LabAnalysisResult
from Domain.enums import Department, InputType

_MIME_JPEG = "image/jpeg"
from Domain.prompts import (
    LAB_SYNTHESIS_SYSTEM, build_lab_synthesis_prompt,
    LAB_TABULAR_SYNTHESIS_SYSTEM, build_lab_tabular_synthesis_prompt,
)
from Domain.interfaces import ILLMClient, IVisionClient, IClinicalClient, IRetriever
from infrastructure.config import get_settings
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vision-key routing
# ---------------------------------------------------------------------------

# test_name substring patterns → vision prompt key (checked BEFORE dept fallback)
# Patterns are matched case-insensitively against the full test_name string.
_TEST_NAME_PATTERNS: list[tuple[str, str]] = [
    # CT chest / lung / thorax
    (r"ct\b.*(?:chest|thorax|lung|pulmonary)",   "ct_chest"),
    (r"(?:chest|thorax|lung|pulmonary).*\bct\b", "ct_chest"),
    (r"hrct",                                     "ct_chest"),
    (r"low.?dose\b.*lung",                        "ct_chest"),
    # Chest X-ray / CXR
    (r"chest\s*x.?ray|\bcxr\b|pa\s*view|ap\s*view.*chest|chest.*ap\b", "chest_xray"),
    # CT abdomen / pelvis
    (r"ct\b.*(?:abdomen|abdominal|pelvis|pelvic|liver|renal|kidney)", "abdominal_xray"),
    (r"(?:abdomen|pelvis).*\bct\b",                                    "abdominal_xray"),
    # CT brain / head
    (r"ct\b.*(?:brain|head|cranial|cerebral|neuro)",  "ct_brain"),
    (r"(?:brain|head).*\bct\b",                       "ct_brain"),
    # MRI brain / head
    (r"mri\b.*(?:brain|head|cranial|cerebral|neuro)", "brain_mri"),
    (r"(?:brain|head).*\bmri\b",                      "brain_mri"),
    # MRI spine
    (r"mri\b.*spine|spine.*\bmri\b",  "spine_xray"),
    # Ultrasound abdomen
    (r"(?:ultrasound|usg)\b.*(?:abdomen|abdominal|pelvis|pelvic)", "ultrasound_abdomen"),
    (r"(?:abdomen|abdominal|pelvis).*(?:ultrasound|usg)\b",        "ultrasound_abdomen"),
    # ECG / EKG
    (r"\b(?:ecg|ekg|electrocardiog)", "ecg"),
    # Fundus / retinal
    (r"fundus|retinal|ophthalmoscopy|funduscopy", "fundus"),
    # Abdominal X-ray (non-CT)
    (r"abdominal\s*x.?ray|kub\b", "abdominal_xray"),
    # Bone / joint X-ray
    (r"(?:bone|joint|hip|knee|shoulder|wrist|ankle|foot|hand).*x.?ray", "bone_xray"),
    (r"x.?ray.*(?:bone|joint|hip|knee|shoulder|wrist|ankle)",           "bone_xray"),
    # Skull X-ray
    (r"skull\s*x.?ray", "skull_xray"),
    # Spine X-ray (non-CT)
    (r"spine\s*x.?ray|(?:cervical|lumbar|thoracic)\s*spine", "spine_xray"),
    # Skin / dermatology
    (r"skin\s*lesion|dermoscopy|dermatoscopy", "skin_lesion"),
    # Blood panels & lab tests
    (r"\b(?:cbc|complete\s*blood|full\s*blood|metabolic\s*panel|lipid|thyroid|coagulation|hba1c|renal|liver|kidney|glucose)\b", "blood_panel"),
]

# Compiled once at module load
_COMPILED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(pat, re.IGNORECASE), key) for pat, key in _TEST_NAME_PATTERNS
]

# Department fallback (used when no test_name pattern matches)
_DEPT_TO_VISION_KEY: dict[str, str] = {
    "respiratory":       "chest_xray",
    "cardiology":        "ecg",
    "dermatology":       "skin_lesion",
    "neurology":         "brain_mri",
    "ophthalmology":     "fundus",
    "hematology":        "blood_panel",
    "nephrology":        "blood_panel",
    "endocrinology":     "blood_panel",
    "internal_medicine": "abdominal_xray",
    "radiology":         "bone_xray",
}


def _resolve_vision_key(test_name: str, department: Department) -> str:
    """Return the best vision-prompt key for this order.

    Resolution order:
    1. Exact match against ``_TEST_NAME_PATTERNS`` (case-insensitive regex).
    2. Department fallback via ``_DEPT_TO_VISION_KEY``.
    3. Hard fallback: ``"blood_panel"``.
    """
    if test_name:
        for pattern, key in _COMPILED_PATTERNS:
            if pattern.search(test_name):
                logger.debug("Vision key resolved from test_name '%s' → '%s'", test_name, key)
                return key

    dept_key = _DEPT_TO_VISION_KEY.get(department.value, "blood_panel")
    logger.debug("Vision key resolved from department '%s' → '%s'", department.value, dept_key)
    return dept_key


class LabAnalysisUseCase:
    """
    Tier 2: Doctor orders lab → async pipeline:
    (fetch image) → Gemini extract findings → Groq synthesize draft.
    Called from Celery task — NOT from HTTP request directly.
    """

    def __init__(self, llm: ILLMClient, gemini: IVisionClient,
                 clinical: IClinicalClient,
                 retriever: Optional[IRetriever] = None):
        self._llm       = llm
        self._gemini    = gemini
        self._clinical  = clinical
        self._retriever = retriever

    async def execute(self, request: LabAnalysisRequest) -> LabAnalysisResult:
        settings = get_settings()

        context = await self._clinical.get_patient_context(
            request.patient_id,
            x_user_id=request.patient_id,
            x_user_role="doctor",
        )

        vision_key = _resolve_vision_key(request.test_name, request.department)

        if request.input_type == InputType.TABULAR and request.tabular_data:
            findings = await self._gemini.extract_tabular(
                request.tabular_data, vision_key
            )
        else:
            try:
                image_bytes = await self._download_file(request.file_url)
            except Exception as exc:
                logger.warning(
                    "Failed to download file from %s for result_id=%s: %s — "
                    "falling back to manual review.",
                    request.file_url, request.result_id, exc,
                )
                return LabAnalysisResult(
                    result_id=request.result_id,
                    visual_findings=None,
                    draft_text=(
                        "⚠️ Unable to access the uploaded file for AI analysis. "
                        "Please review the result manually."
                    ),
                    confidence=0.0,
                    citations=[],
                    requires_specialist_review=True,
                    model_versions={
                        "vision": settings.GEMINI_VISION_MODEL,
                        "text":   settings.GROQ_TEXT_MODEL,
                    },
                )
            mime_type   = self._detect_mime(request.file_url)
            findings    = await self._gemini.extract_findings(
                image_bytes, mime_type, vision_key
            )

        if findings.get("error"):
            logger.warning(f"Vision extraction failed for {request.result_id}")
            return LabAnalysisResult(
                result_id=request.result_id,
                visual_findings=None,
                draft_text="⚠️ Unable to extract data from file. Manual review required.",
                confidence=0.0,
                citations=[],
                requires_specialist_review=True,
                model_versions={
                    "vision": settings.GEMINI_VISION_MODEL,
                    "text":   settings.GROQ_TEXT_MODEL,
                },
            )

        rag_context = ""
        if self._retriever:
            keywords = " ".join(findings.get("keywords", [])[:5])
            query    = f"{request.test_name} {keywords}".strip()
            rag_context = await self._retriever.get_context(
                query, department=request.department.value, top_k=3
            )

        # Tabular path (blood panels, CSV): scoped prompt — no clinical notes context
        if request.input_type == InputType.TABULAR:
            user_prompt = build_lab_tabular_synthesis_prompt(
                findings, context, request.test_name, rag_context=rag_context
            )
            draft_text = await self._llm.complete(
                system_prompt=LAB_TABULAR_SYNTHESIS_SYSTEM,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=2048,
            )
        else:
            user_prompt = build_lab_synthesis_prompt(
                findings, context, request.test_name, rag_context=rag_context
            )
            draft_text = await self._llm.complete(
                system_prompt=LAB_SYNTHESIS_SYSTEM,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=2048,
            )

        confidence = float(findings.get("confidence", 0.7))
        is_fallback = bool(findings.get("_fallback"))
        # Flag for specialist review: low confidence OR AI used text-only fallback
        requires_specialist = is_fallback or confidence < 0.5

        return LabAnalysisResult(
            result_id=request.result_id,
            visual_findings=findings,
            draft_text=draft_text,
            confidence=confidence,
            citations=[],
            requires_specialist_review=requires_specialist,
            model_versions={
                "vision": settings.GEMINI_VISION_MODEL,
                "text":   settings.GROQ_TEXT_MODEL,
            },
        )

    @staticmethod
    async def _download_file(url: str) -> bytes:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content

    @staticmethod
    def _detect_mime(url: str) -> str:
        url_lower = url.lower()
        if url_lower.endswith(".png"):
            return "image/png"
        if url_lower.endswith(".jpg") or url_lower.endswith(".jpeg"):
            return _MIME_JPEG
        if url_lower.endswith(".dicom") or url_lower.endswith(".dcm"):
            return _MIME_JPEG
        if url_lower.endswith(".pdf"):
            return "application/pdf"
        return "application/octet-stream"

