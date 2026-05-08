from datetime import datetime, timezone
from uuid import UUID

from Application.dtos import LabResultResponse, UpdateAIDraftRequest
from Application.exceptions import LabResultNotFoundError
from Domain.interfaces.lab_order_repository import ILabOrderRepository
from Domain.interfaces.lab_result_repository import ILabResultRepository
from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.test_type import TestType

# Departments where a specialist (not the ordering GP) should review the result.
# Matches the Department enum values in AI Service.
_SPECIALTY_DEPARTMENTS = frozenset({
    "radiology",
    "cardiology",
    "neurology",
    "ophthalmology",
    "dermatology",
    "respiratory",
    "nephrology",
    "hematology",
    "endocrinology",
})

# Test types that always route to a specialist regardless of department label.
_SPECIALTY_TEST_TYPES = frozenset({
    TestType.IMAGING,
    TestType.CHEST_XRAY,
    TestType.BONE_XRAY,
    TestType.ABDOMINAL_XRAY,
    TestType.SKULL_XRAY,
    TestType.SPINE_XRAY,
    TestType.ECG,
})

# Map test_type → implied specialty (used when department is not set)
_TEST_TYPE_TO_SPECIALTY = {
    TestType.ECG:            "cardiology",
    TestType.IMAGING:        "radiology",
    TestType.CHEST_XRAY:     "radiology",
    TestType.BONE_XRAY:      "radiology",
    TestType.ABDOMINAL_XRAY: "radiology",
    TestType.SKULL_XRAY:     "radiology",
    TestType.SPINE_XRAY:     "radiology",
}


def _resolve_specialty(department: str | None, test_type) -> str | None:
    """Return the required specialty for a lab order, or None for general tests."""
    if department and department in _SPECIALTY_DEPARTMENTS:
        return department
    if test_type and test_type in _SPECIALTY_TEST_TYPES:
        return _TEST_TYPE_TO_SPECIALTY.get(test_type, department)
    return None


class UpdateAIDraftUseCase:
    """Apply AI pipeline output to a LabResult record.

    Accepts results in PENDING or AI_PROCESSING status.
    Transitions: PENDING → AI_PROCESSING → AI_DRAFT → DOCTOR_REVIEW

    Reviewer routing (set here, once, after AI finishes):
    - General test  → reviewer_doctor_id = order.doctor_id (ordering doctor reviews)
    - Specialty test → reviewer_doctor_id = None           (open-claim for specialists)
    """

    def __init__(
        self,
        result_repo: ILabResultRepository,
        order_repo: ILabOrderRepository,
    ) -> None:
        self._result_repo = result_repo
        self._order_repo = order_repo

    async def execute(
        self,
        result_id: UUID,
        request: UpdateAIDraftRequest,
    ) -> LabResultResponse:
        result = await self._result_repo.get_by_id(result_id)
        if result is None:
            raise LabResultNotFoundError()

        # Allow idempotent call if AI already processed (e.g. Celery retry)
        if result.status == LabResultStatus.AI_DRAFT:
            pass  # Will be overwritten below
        elif result.status == LabResultStatus.PENDING:
            result.transition_to(LabResultStatus.AI_PROCESSING)
        elif result.status != LabResultStatus.AI_PROCESSING:
            raise ValueError(
                f"Cannot apply AI draft: result is in status '{result.status}'. "
                "Expected PENDING or AI_PROCESSING."
            )

        result.apply_ai_draft(
            visual_findings=request.ai_visual_findings,
            draft_text=request.ai_draft_text,
            citations=request.ai_draft_citations,
            confidence=request.ai_confidence,
            model_versions=request.ai_model_versions or {},
            processed_at=datetime.now(tz=timezone.utc),
        )

        # Advance status: low-confidence / fallback → NEEDS_MANUAL_REVIEW (open-claim)
        #                  normal result             → DOCTOR_REVIEW
        if request.requires_specialist_review:
            result.transition_to(LabResultStatus.NEEDS_MANUAL_REVIEW)
        else:
            # Advance to DOCTOR_REVIEW so the verify endpoint is immediately usable
            result.transition_to(LabResultStatus.DOCTOR_REVIEW)

        # --- Specialist routing: set once, never overwritten after this point ---
        # Only set if not already assigned (idempotent retry safety)
        if result.reviewer_doctor_id is None and result.required_specialty is None:
            order = await self._order_repo.get_by_id(result.order_id)
            if order is not None:
                specialty = _resolve_specialty(order.department, order.test_type)
                if specialty or request.requires_specialist_review:
                    # Specialty test OR AI flagged low-confidence → open claim
                    result.required_specialty = specialty or "general"
                    result.reviewer_doctor_id = None
                else:
                    # General test, AI confident → ordering doctor is the reviewer
                    result.reviewer_doctor_id = order.doctor_id

        saved = await self._result_repo.save(result)
        return LabResultResponse.model_validate(saved)
