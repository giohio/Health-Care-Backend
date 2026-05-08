from uuid import UUID

from Application.dtos import LabResultResponse
from Application.exceptions import (
    LabResultNotFoundError,
    ResultAlreadyClaimedError,
    ResultNotClaimableError,
)
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus


class ClaimLabResultUseCase:
    """Specialist claims an open-claim lab result.

    Open-claim results have ``required_specialty`` set but ``reviewer_doctor_id``
    is None — they appear on the specialty worklist for all doctors with that
    specialty.  Once claimed, only the claiming doctor (or admin) may verify.

    Rules:
    - Result must be in DOCTOR_REVIEW or NEEDS_MANUAL_REVIEW.
    - reviewer_doctor_id must be None (not yet claimed).
    - required_specialty must match the calling doctor's specialty (enforced
      at the route level via the X-Doctor-Specialty header; the use case itself
      only handles the domain state change).
    """

    def __init__(self, result_repo: ILabResultRepository) -> None:
        self._result_repo = result_repo

    async def execute(
        self,
        result_id: UUID,
        doctor_id: UUID,
    ) -> LabResultResponse:
        result = await self._result_repo.get_by_id(result_id)
        if result is None:
            raise LabResultNotFoundError()

        if result.required_specialty is None:
            raise ResultNotClaimableError(
                "This is a general test — it is already assigned to the ordering doctor."
            )

        if result.reviewer_doctor_id is not None:
            raise ResultAlreadyClaimedError()

        if result.status not in (
            LabResultStatus.DOCTOR_REVIEW,
            LabResultStatus.NEEDS_MANUAL_REVIEW,
        ):
            raise ResultNotClaimableError(
                f"Expected DOCTOR_REVIEW or NEEDS_MANUAL_REVIEW (current: {result.status})."
            )

        result.claim(doctor_id)
        saved = await self._result_repo.save(result)
        return LabResultResponse.model_validate(saved)
