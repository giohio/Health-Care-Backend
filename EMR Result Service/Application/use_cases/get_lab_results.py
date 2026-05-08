import uuid
from typing import List, Optional

from Application.dtos import LabResultResponse, PatientLabResultResponse
from Application.exceptions import LabResultNotFoundError, ResultNotAccessibleError
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus


class ListLabResultsUseCase:
    """List lab results.

    Patients only see PUBLISHED results; doctors/admins see all statuses.

    Specialty worklist usage:
    - Pass ``required_specialty="radiology"`` + ``open_claim=True`` to get
      unclaimed radiology results (i.e. the specialist worklist).
    - Pass ``reviewer_doctor_id=<my_id>`` to get results assigned to a doctor.
    """

    def __init__(self, result_repo: ILabResultRepository):
        self.result_repo = result_repo

    async def execute(
        self,
        caller_role: str,
        patient_id: Optional[uuid.UUID] = None,
        doctor_id: Optional[uuid.UUID] = None,
        status: Optional[LabResultStatus] = None,
        reviewer_doctor_id: Optional[uuid.UUID] = None,
        required_specialty: Optional[str] = None,
        open_claim: Optional[bool] = None,
    ) -> List[LabResultResponse]:
        # Patients may only see published results
        effective_status = status
        if caller_role == "patient":
            effective_status = LabResultStatus.PUBLISHED

        results = await self.result_repo.list(
            patient_id=patient_id,
            doctor_id=doctor_id,
            status=effective_status,
            reviewer_doctor_id=reviewer_doctor_id,
            required_specialty=required_specialty,
            open_claim=open_claim,
        )
        return [LabResultResponse.model_validate(r, from_attributes=True) for r in results]


class GetLabResultUseCase:
    """Fetch a single lab result.

    Patients can only access PUBLISHED results.
    """

    def __init__(self, result_repo: ILabResultRepository):
        self.result_repo = result_repo

    async def execute(
        self,
        result_id: uuid.UUID,
        caller_role: str,
    ) -> LabResultResponse:
        result = await self.result_repo.get_by_id(result_id)
        if result is None:
            raise LabResultNotFoundError()
        if caller_role == "patient" and result.status != LabResultStatus.PUBLISHED:
            raise ResultNotAccessibleError()
        return LabResultResponse.model_validate(result, from_attributes=True)
