from fastapi import APIRouter, Header, Depends, HTTPException
from presentation.schema import SoapDraftInput
from Application.soap_draft import SoapDraftUseCase
from presentation.dependencies import get_soap_draft_usecase
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/soap-draft", tags=["AI - SOAP Note"])


@router.post("")
async def generate_soap_draft(
    body:          SoapDraftInput,
    x_user_id:     str | None = Header(None),
    x_user_role:   str | None = Header(None),
    authorization: str | None = Header(None),
    use_case:      SoapDraftUseCase = Depends(get_soap_draft_usecase),
):
    """
    Generate a professional SOAP note draft based on patient clinical record and labs.
    Restricted to doctors and admins.
    """
    if x_user_role not in ("doctor", "admin"):
        raise HTTPException(status_code=403, detail="Only doctors can access SOAP drafts")

    token = authorization.replace("Bearer ", "") if authorization else ""

    try:
        draft = await use_case.execute(
            patient_id=body.patient_id,
            token=token,
            x_user_id=x_user_id,
            x_user_role=x_user_role,
            triage_session_id=body.triage_session_id
        )
        return draft
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="AI SOAP draft timed out. Please retry with fewer records or try again shortly.",
        )
    except Exception as e:
        logger.error("SOAP draft generation error: %s", e)
        raise HTTPException(status_code=500, detail="Unable to generate SOAP draft.")
