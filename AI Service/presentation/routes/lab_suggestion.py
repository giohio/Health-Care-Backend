from fastapi import APIRouter, Header, Depends, HTTPException
from Application.lab_suggestion import LabSuggestionUseCase
from presentation.schema import LabSuggestionInput
from presentation.dependencies import get_lab_suggestion_usecase

router = APIRouter(prefix="/suggest-lab-tests", tags=["AI - Lab Suggestions"])


@router.post("")
async def suggest_lab_tests(
    body:        LabSuggestionInput,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
    use_case:    LabSuggestionUseCase = Depends(get_lab_suggestion_usecase),
):
    """
    **Doctors only.** Given a patient's symptoms, return AI-suggested lab tests.

    Response is a JSON object with a `suggestions` array.
    Each item has: `test_name`, `test_type`, `reason`, `priority`.
    These are SUGGESTIONS for physician review — not clinical orders.
    """
    if x_user_role not in ("doctor", "admin"):
        raise HTTPException(status_code=403, detail="Only doctors can request lab suggestions.")

    return await use_case.execute(
        symptoms=body.symptoms,
        x_user_id=x_user_id,
        x_user_role=x_user_role,
        patient_id=body.patient_id,
        department=body.department,
    )
