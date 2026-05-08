"""POST /analyze-all-labs — enqueues holistic synthesis Celery task."""
import logging
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Holistic Lab Analysis"])


class AnalyzeAllLabsRequest(BaseModel):
    appointment_id: str
    patient_id: str
    summary_id: str


@router.post(
    "/analyze-all-labs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue holistic cross-result analysis for a completed appointment",
)
async def analyze_all_labs(
    body: AnalyzeAllLabsRequest,
    x_user_role: str = Header(default="service"),
):
    """
    Called by EMR Result Service after all lab results for an appointment reach PUBLISHED.
    Enqueues ``analyze_all_labs_task`` and returns 202 immediately.
    """
    if x_user_role not in ("service", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service or admin role may trigger holistic analysis.",
        )

    from infrastructure.celery.tasks import analyze_all_labs_task

    analyze_all_labs_task.delay(
        {
            "appointment_id": body.appointment_id,
            "patient_id": body.patient_id,
            "summary_id": body.summary_id,
        }
    )
    logger.info(
        "Holistic analysis enqueued appointment_id=%s summary_id=%s",
        body.appointment_id,
        body.summary_id,
    )
    return {"queued": True, "appointment_id": body.appointment_id}
