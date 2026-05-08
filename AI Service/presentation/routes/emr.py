from fastapi import APIRouter, Header, Depends, HTTPException
from fastapi.responses import StreamingResponse
from presentation.schema import EmrSummaryInput
from Domain.entities import EmrSummaryRequest
from Application.emr_summary import EmrSummaryUseCase
from presentation.dependencies import get_emr_summary_usecase
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/summarize-emr", tags=["AI - EMR Summary"])


@router.post("")
async def summarize_emr(
    body:          EmrSummaryInput,
    x_user_id:     str = Header(...),
    x_user_role:   str = Header(...),
    authorization: str | None = Header(None),
    use_case:      EmrSummaryUseCase = Depends(get_emr_summary_usecase),
):
    """
    Tier 2 on-demand — streaming SSE.
    Doctor opens EMR → AI streams patient summary.
    Only doctors and admins can call this endpoint.
    """
    if x_user_role not in ("doctor", "admin"):
        raise HTTPException(status_code=403, detail="Only doctors can access EMR summaries")

    token   = authorization.replace("Bearer ", "") if authorization else ""
    request = EmrSummaryRequest(
        patient_id = body.patient_id,
        doctor_id  = x_user_id,
        language   = body.language,
    )

    async def event_stream():
        try:
            async for chunk in use_case.execute(request, token, x_user_id, x_user_role):
                safe = chunk.replace("\n", "\ndata: ")
                yield f"data: {safe}\n\n"
        except Exception as e:
            logger.error("EMR summary stream error: %s", e)
            yield "data: [ERROR] Unable to generate EMR summary.\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
