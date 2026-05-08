import json
import uuid

from Application.dtos import CreateLabResultRequest, LabResultResponse
from Application.exceptions import LabOrderNotFoundError
from Domain.entities.lab_result import LabResult
from Domain.interfaces.lab_order_repository import ILabOrderRepository
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus


class UploadLabResultUseCase:
    """Create a LabResult record after file upload or manual entry.

    File upload path:  persists record with PENDING status; AI pipeline is triggered
                       asynchronously by the caller (Celery task).
    Manual entry path: serialises manual_entries to ai_draft_text, sets status to
                       DOCTOR_REVIEW immediately (Option A — no AI queue).
    """

    def __init__(
        self,
        order_repo: ILabOrderRepository,
        result_repo: ILabResultRepository,
    ):
        self.order_repo = order_repo
        self.result_repo = result_repo

    async def execute(self, request: CreateLabResultRequest) -> LabResultResponse:
        order = await self.order_repo.get_by_id(request.order_id)
        if order is None:
            raise LabOrderNotFoundError()

        if request.file_type == "manual":
            entries_json = json.dumps(
                [e.model_dump() for e in (request.manual_entries or [])],
                ensure_ascii=False,
                indent=2,
            )
            result = LabResult(
                id=uuid.uuid4(),
                order_id=request.order_id,
                patient_id=request.patient_id,
                doctor_id=request.doctor_id,
                file_url=None,
                file_type="manual",
                status=LabResultStatus.PENDING,  # AI will process and advance to DOCTOR_REVIEW
                raw_input_json=entries_json,      # permanent storage — never overwritten by AI
                ai_draft_text=None,              # will be set by AI pipeline
                doctor_notes=request.notes,
            )
        else:
            result = LabResult(
                id=uuid.uuid4(),
                order_id=request.order_id,
                patient_id=request.patient_id,
                doctor_id=request.doctor_id,
                file_url=request.file_url,
                file_type=request.file_type,
                status=LabResultStatus.PENDING,
            )

        saved = await self.result_repo.save(result)
        return LabResultResponse.model_validate(saved, from_attributes=True)
