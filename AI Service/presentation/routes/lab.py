from fastapi import APIRouter, Header
from presentation.schema import TriggerLabAnalysisInput
from infrastructure.celery.tasks import analyze_lab_task

router = APIRouter(prefix="/analyze-lab", tags=["AI - Lab Analysis"])


@router.post("")
async def trigger_lab_analysis(
    body:        TriggerLabAnalysisInput,
    x_user_id:   str | None = Header(None),
    x_user_role: str | None = Header(None),
):
    """
    Tier 2 async — enqueue Celery job.
    Returns immediately with a job ID.
    Called by emr_result_service internally after file upload.
    """
    analyze_lab_task.delay({
        "result_id":    body.result_id,
        "patient_id":   body.patient_id,
        "file_url":     body.file_url,
        "input_type":   body.input_type,
        "department":   body.department,
        "test_name":    body.test_name,
        "tabular_data": body.tabular_data,
        "auth_token":   body.auth_token,
        "x_user_id":    x_user_id,
        "x_user_role":  x_user_role,
    })

    return {
        "status":    "queued",
        "result_id": body.result_id,
        "message":   "Lab analysis job enqueued. Result will be available when complete.",
    }
