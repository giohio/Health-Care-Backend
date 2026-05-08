from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from Domain.value_objects.lab_result_status import LabResultStatus


# Valid status transitions for the Human-in-the-Loop lifecycle
_VALID_TRANSITIONS: dict[LabResultStatus, list[LabResultStatus]] = {
    LabResultStatus.PENDING: [
        LabResultStatus.AI_PROCESSING,
        LabResultStatus.NEEDS_MANUAL_REVIEW,
    ],
    LabResultStatus.AI_PROCESSING: [
        LabResultStatus.AI_DRAFT,
        LabResultStatus.NEEDS_MANUAL_REVIEW,
    ],
    LabResultStatus.AI_DRAFT: [
        LabResultStatus.AI_DRAFT,
        LabResultStatus.DOCTOR_REVIEW,
        LabResultStatus.NEEDS_MANUAL_REVIEW,
    ],
    LabResultStatus.DOCTOR_REVIEW: [
        LabResultStatus.PUBLISHED,
        LabResultStatus.NEEDS_MANUAL_REVIEW,
    ],
    LabResultStatus.NEEDS_MANUAL_REVIEW: [
        LabResultStatus.PENDING,
        LabResultStatus.PUBLISHED,
    ],
    LabResultStatus.PUBLISHED: [],
}


@dataclass
class LabResult:
    id: UUID
    order_id: UUID
    patient_id: UUID
    doctor_id: UUID
    status: LabResultStatus = LabResultStatus.PENDING

    # File storage
    file_url: Optional[str] = None
    file_type: Optional[str] = None

    # Raw input data (manual entries JSON) — permanent, never overwritten by AI
    raw_input_json: Optional[str] = None

    # Specialist review routing
    # None  → open-claim (any doctor with matching specialty can claim it)
    # set   → only that doctor (or admin) may verify
    reviewer_doctor_id: Optional[UUID] = None
    # The specialty required to claim this result (e.g. "radiology").
    # None for general tests that go directly back to the ordering doctor.
    required_specialty: Optional[str] = None

    # AI output fields
    ai_visual_findings: Optional[Dict[str, Any]] = None
    ai_draft_text: Optional[str] = None
    ai_draft_citations: Optional[Dict[str, Any]] = None
    ai_confidence: Optional[float] = None
    ai_model_versions: Optional[Dict[str, Any]] = None
    ai_processed_at: Optional[datetime] = None

    # Doctor review fields
    doctor_notes: Optional[str] = None
    verified_by: Optional[UUID] = None
    verified_at: Optional[datetime] = None

    # Published content (visible to patient)
    published_text: Optional[str] = None
    published_findings: Optional[Dict[str, Any]] = None
    published_at: Optional[datetime] = None

    created_at: Optional[datetime] = None

    def can_transition_to(self, target: LabResultStatus) -> bool:
        return target in _VALID_TRANSITIONS.get(self.status, [])

    def transition_to(self, target: LabResultStatus) -> None:
        if not self.can_transition_to(target):
            raise ValueError(
                f"Invalid lab result status transition: {self.status} -> {target}"
            )
        self.status = target

    def apply_ai_draft(
        self,
        visual_findings: Optional[Dict[str, Any]],
        draft_text: str,
        citations: Optional[Dict[str, Any]],
        confidence: float,
        model_versions: Dict[str, Any],
        processed_at: datetime,
    ) -> None:
        """Apply AI pipeline output and advance status to AI_DRAFT."""
        self.transition_to(LabResultStatus.AI_DRAFT)
        self.ai_visual_findings = visual_findings
        self.ai_draft_text = draft_text
        self.ai_draft_citations = citations
        self.ai_confidence = confidence
        self.ai_model_versions = model_versions
        self.ai_processed_at = processed_at

    def claim(self, doctor_id: UUID) -> None:
        """Specialist claims an open-claim result (reviewer_doctor_id is None).

        After claiming, only this doctor (or admin) can verify and publish.
        Only allowed when the result is in DOCTOR_REVIEW and has no reviewer yet.
        """
        if self.reviewer_doctor_id is not None:
            raise ValueError("This result has already been claimed.")
        if self.status not in (LabResultStatus.DOCTOR_REVIEW, LabResultStatus.NEEDS_MANUAL_REVIEW):
            raise ValueError(
                f"Can only claim results in DOCTOR_REVIEW or NEEDS_MANUAL_REVIEW "
                f"(current: {self.status})."
            )
        self.reviewer_doctor_id = doctor_id

    def publish(
        self,
        verified_by: UUID,
        verified_at: datetime,
        published_at: datetime,
        doctor_notes: Optional[str] = None,
        published_text: Optional[str] = None,
        published_findings: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Doctor verifies and publishes the result to the patient."""
        if self.status not in (LabResultStatus.DOCTOR_REVIEW, LabResultStatus.NEEDS_MANUAL_REVIEW):
            raise ValueError(
                f"Result must be in DOCTOR_REVIEW or NEEDS_MANUAL_REVIEW to publish "
                f"(current: {self.status})."
            )
        self.verified_by = verified_by
        self.verified_at = verified_at
        self.doctor_notes = doctor_notes
        self.published_text = published_text or self.ai_draft_text
        self.published_findings = published_findings
        self.published_at = published_at
        self.status = LabResultStatus.PUBLISHED
