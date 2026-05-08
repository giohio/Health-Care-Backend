from fastapi import APIRouter, Header, Depends, HTTPException
from Application.treatment_plan import TreatmentPlanUseCase
from presentation.schema import TreatmentPlanInput
from presentation.dependencies import get_treatment_plan_usecase

router = APIRouter(prefix="/treatment-plan", tags=["AI - Treatment Plan"])

_DOCTOR_ROLES = {"doctor", "admin"}


@router.post("")
async def generate_treatment_plan(
    body:        TreatmentPlanInput,
    x_user_id:   str = Header(...),
    x_user_role: str = Header(...),
    use_case:    TreatmentPlanUseCase = Depends(get_treatment_plan_usecase),
):
    """
    **Doctors only.** Generate an AI treatment plan from lab result summary + clinical context.

    Response is a JSON object with:
    - `summary`: Clinical overview (2–4 sentences).
    - `urgency`: one of ROUTINE / URGENT / EMERGENCY.
    - `follow_up_days`: integer or null.
    - `recommendations`: list of `{category, text}` items.

    These are AI SUGGESTIONS for physician review — not clinical orders.
    """
    if x_user_role not in _DOCTOR_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Treatment plan generation is restricted to doctors and admins.",
        )

    return await use_case.execute(
        lab_summary=body.lab_summary,
        x_user_id=x_user_id,
        x_user_role=x_user_role,
        patient_id=body.patient_id,
        symptoms=body.symptoms,
    )
