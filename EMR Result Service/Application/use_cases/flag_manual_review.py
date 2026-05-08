import uuid

from Application.dtos import LabResultResponse
from Application.exceptions import LabResultNotFoundError
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus


class FlagManualReviewUseCase:
    """Doctor flags a lab result for manual review (e.g., AI output unreliable)."""

    def __init__(self, result_repo: ILabResultRepository):
        self.result_repo = result_repo

    async def execute(self, result_id: uuid.UUID) -> LabResultResponse:
        result = await self.result_repo.get_by_id(result_id)
        if result is None:
            raise LabResultNotFoundError()

        result.transition_to(LabResultStatus.NEEDS_MANUAL_REVIEW)
        saved = await self.result_repo.save(result)
        return LabResultResponse.model_validate(saved, from_attributes=True)
