from typing import Annotated, List, Optional
from uuid import UUID

from Application.dtos import (
    ClinicalNoteResponse,
    CreateClinicalNoteRequest,
    UpdateClinicalNoteContentRequest,
    CreateDiagnosisRequest,
    CreateMedicationRequest,
    DiagnosisResponse,
    MedicationResponse,
    PatientSummaryResponse,
    UpdateDiagnosisRequest,
    UpdateMedicationStatusRequest,
    VaccinationResponse,
)
from Application.exceptions import DiagnosisNotFoundError, MedicationNotFoundError
from Application.use_cases.add_diagnosis import AddDiagnosisUseCase
from Application.use_cases.clinical_notes import CreateClinicalNoteUseCase, ListClinicalNotesUseCase, UpdateClinicalNoteUseCase
from Application.use_cases.get_patient_summary import GetPatientSummaryUseCase
from Application.use_cases.list_diagnoses import ListDiagnosesUseCase
from Application.use_cases.list_medications import ListMedicationsUseCase
from Application.use_cases.list_vaccinations import ListVaccinationsUseCase
from Application.use_cases.prescribe_medication import PrescribeMedicationUseCase
from Application.use_cases.update_diagnosis import UpdateDiagnosisUseCase
from Application.use_cases.update_medication_status import UpdateMedicationStatusUseCase
from Domain.value_objects.diagnosis_status import DiagnosisStatus
from Domain.value_objects.medication_status import MedicationStatus
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from presentation.dependencies import (
    get_add_diagnosis_use_case,
    get_create_note_use_case,
    get_update_note_use_case,
    get_list_diagnoses_use_case,
    get_list_medications_use_case,
    get_list_notes_use_case,
    get_list_vaccinations_use_case,
    get_patient_summary_use_case,
    get_prescribe_medication_use_case,
    get_update_diagnosis_use_case,
    get_update_medication_status_use_case,
)

router = APIRouter(tags=["Clinical"])

MISSING_USER_ID = "X-User-Id header is missing"
MISSING_ROLE = "X-User-Role header is missing"
ACCESS_DENIED = "Access denied."


def _require_user_id(x_user_id: UUID | None) -> UUID:
    if not x_user_id:
        raise HTTPException(status_code=401, detail=MISSING_USER_ID)
    return x_user_id


def _require_role(x_user_role: str | None, allowed: list[str]) -> str:
    if not x_user_role:
        raise HTTPException(status_code=401, detail=MISSING_ROLE)
    if x_user_role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient role.")
    return x_user_role


# ---------------------------------------------------------------------------
# Patient summary
# ---------------------------------------------------------------------------


@router.get(
    "/patients/{patient_id}/summary",
    response_model=PatientSummaryResponse,
    summary="Get full clinical summary for a patient",
)
async def get_patient_summary(
    patient_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: GetPatientSummaryUseCase = Depends(get_patient_summary_use_case),
):
    user_id = _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "patient", "admin"])
    # Patients may only fetch their own summary
    if role == "patient" and user_id != patient_id:
        raise HTTPException(status_code=403, detail=ACCESS_DENIED)
    return await use_case.execute(patient_id)


# ---------------------------------------------------------------------------
# Diagnoses
# ---------------------------------------------------------------------------


@router.get(
    "/patients/{patient_id}/diagnoses",
    response_model=List[DiagnosisResponse],
    summary="List patient diagnoses",
)
async def list_diagnoses(
    patient_id: UUID,
    status: Optional[DiagnosisStatus] = Query(None),
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: ListDiagnosesUseCase = Depends(get_list_diagnoses_use_case),
):
    user_id = _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "patient", "admin"])
    if role == "patient" and user_id != patient_id:
        raise HTTPException(status_code=403, detail=ACCESS_DENIED)
    return await use_case.execute(patient_id, status=status)


@router.post(
    "/patients/{patient_id}/diagnoses",
    response_model=DiagnosisResponse,
    status_code=201,
    summary="Doctor adds a diagnosis",
)
async def add_diagnosis(
    patient_id: UUID,
    body: CreateDiagnosisRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: AddDiagnosisUseCase = Depends(get_add_diagnosis_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    # Inject path-param patient_id into request
    body = body.model_copy(update={"patient_id": patient_id})
    return await use_case.execute(body)


@router.patch(
    "/patients/{patient_id}/diagnoses/{diagnosis_id}",
    response_model=DiagnosisResponse,
    summary="Update a diagnosis",
)
async def update_diagnosis(
    patient_id: UUID,
    diagnosis_id: UUID,
    body: UpdateDiagnosisRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: UpdateDiagnosisUseCase = Depends(get_update_diagnosis_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    try:
        return await use_case.execute(diagnosis_id, body)
    except DiagnosisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Medications
# ---------------------------------------------------------------------------


@router.get(
    "/patients/{patient_id}/medications",
    response_model=List[MedicationResponse],
    summary="List patient medications",
)
async def list_medications(
    patient_id: UUID,
    status: Optional[MedicationStatus] = Query(None),
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: ListMedicationsUseCase = Depends(get_list_medications_use_case),
):
    user_id = _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "patient", "admin"])
    if role == "patient" and user_id != patient_id:
        raise HTTPException(status_code=403, detail=ACCESS_DENIED)
    return await use_case.execute(patient_id, status=status)


@router.post(
    "/patients/{patient_id}/medications",
    response_model=MedicationResponse,
    status_code=201,
    summary="Doctor prescribes a medication",
)
async def prescribe_medication(
    patient_id: UUID,
    body: CreateMedicationRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: PrescribeMedicationUseCase = Depends(get_prescribe_medication_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    body = body.model_copy(update={"patient_id": patient_id})
    return await use_case.execute(body)


@router.patch(
    "/medications/{medication_id}",
    response_model=MedicationResponse,
    summary="Update medication status (stop / complete)",
)
async def update_medication_status(
    medication_id: UUID,
    body: UpdateMedicationStatusRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: UpdateMedicationStatusUseCase = Depends(get_update_medication_status_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    try:
        return await use_case.execute(medication_id, body)
    except MedicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Clinical Notes
# ---------------------------------------------------------------------------


@router.post(
    "/patients/{patient_id}/notes",
    response_model=ClinicalNoteResponse,
    status_code=201,
    summary="Doctor creates a clinical note",
)
async def create_clinical_note(
    patient_id: UUID,
    body: CreateClinicalNoteRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: CreateClinicalNoteUseCase = Depends(get_create_note_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    body = body.model_copy(update={"patient_id": patient_id})
    return await use_case.execute(body)


@router.patch(
    "/notes/{note_id}",
    response_model=ClinicalNoteResponse,
    summary="Update content of an existing clinical note",
)
async def update_clinical_note(
    note_id: UUID,
    body: UpdateClinicalNoteContentRequest,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: UpdateClinicalNoteUseCase = Depends(get_update_note_use_case),
):
    _require_user_id(x_user_id)
    _require_role(x_user_role, ["doctor", "admin"])
    result = await use_case.execute(note_id, body.content)
    if result is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return result


@router.get(
    "/patients/{patient_id}/notes",
    response_model=List[ClinicalNoteResponse],
    summary="List clinical notes for a patient",
)
async def list_clinical_notes(
    patient_id: UUID,
    appointment_id: Optional[UUID] = Query(None),
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: ListClinicalNotesUseCase = Depends(get_list_notes_use_case),
):
    user_id = _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "patient", "admin"])
    if role == "patient" and user_id != patient_id:
        raise HTTPException(status_code=403, detail=ACCESS_DENIED)
    return await use_case.execute(patient_id, appointment_id=appointment_id)


@router.get(
    "/patients/{patient_id}/vaccinations",
    response_model=List[VaccinationResponse],
    summary="List patient vaccinations",
)
async def list_vaccinations(
    patient_id: UUID,
    x_user_id: UUID | None = Header(None),
    x_user_role: str | None = Header(None),
    use_case: ListVaccinationsUseCase = Depends(get_list_vaccinations_use_case),
):
    user_id = _require_user_id(x_user_id)
    role = _require_role(x_user_role, ["doctor", "patient", "admin"])
    if role == "patient" and user_id != patient_id:
        raise HTTPException(status_code=403, detail=ACCESS_DENIED)
    return await use_case.execute(patient_id)
