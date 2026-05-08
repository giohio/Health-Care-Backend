"""Unit tests for LabResult entity — state machine, transitions, apply_ai_draft, publish."""
import uuid
from datetime import datetime, timezone

import pytest

from Domain.entities.lab_result import LabResult
from Domain.value_objects.lab_result_status import LabResultStatus
from tests.conftest import make_lab_result

NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# State machine — valid transitions
# ---------------------------------------------------------------------------


class TestStateMachineValidTransitions:
    def test_pending_to_ai_processing(self):
        result = make_lab_result(status=LabResultStatus.PENDING)
        result.transition_to(LabResultStatus.AI_PROCESSING)
        assert result.status == LabResultStatus.AI_PROCESSING

    def test_pending_to_needs_manual_review(self):
        result = make_lab_result(status=LabResultStatus.PENDING)
        result.transition_to(LabResultStatus.NEEDS_MANUAL_REVIEW)
        assert result.status == LabResultStatus.NEEDS_MANUAL_REVIEW

    def test_ai_processing_to_ai_draft(self):
        result = make_lab_result(status=LabResultStatus.AI_PROCESSING)
        result.transition_to(LabResultStatus.AI_DRAFT)
        assert result.status == LabResultStatus.AI_DRAFT

    def test_ai_draft_to_doctor_review(self):
        result = make_lab_result(status=LabResultStatus.AI_DRAFT)
        result.transition_to(LabResultStatus.DOCTOR_REVIEW)
        assert result.status == LabResultStatus.DOCTOR_REVIEW

    def test_doctor_review_to_published(self):
        result = make_lab_result(status=LabResultStatus.DOCTOR_REVIEW)
        result.publish(
            verified_by=uuid.uuid4(),
            verified_at=NOW,
            published_at=NOW,
        )
        assert result.status == LabResultStatus.PUBLISHED

    def test_needs_manual_review_to_published(self):
        result = make_lab_result(status=LabResultStatus.NEEDS_MANUAL_REVIEW)
        result.publish(
            verified_by=uuid.uuid4(),
            verified_at=NOW,
            published_at=NOW,
        )
        assert result.status == LabResultStatus.PUBLISHED

    def test_ai_processing_to_needs_manual_review(self):
        result = make_lab_result(status=LabResultStatus.AI_PROCESSING)
        result.transition_to(LabResultStatus.NEEDS_MANUAL_REVIEW)
        assert result.status == LabResultStatus.NEEDS_MANUAL_REVIEW


# ---------------------------------------------------------------------------
# State machine — invalid transitions
# ---------------------------------------------------------------------------


class TestStateMachineInvalidTransitions:
    def test_pending_cannot_go_to_published(self):
        result = make_lab_result(status=LabResultStatus.PENDING)
        with pytest.raises(ValueError):
            result.transition_to(LabResultStatus.PUBLISHED)

    def test_published_is_terminal(self):
        result = make_lab_result(status=LabResultStatus.PUBLISHED)
        for target in LabResultStatus:
            if target != LabResultStatus.PUBLISHED:
                assert not result.can_transition_to(target)

    def test_ai_draft_cannot_go_directly_to_published(self):
        result = make_lab_result(status=LabResultStatus.AI_DRAFT)
        with pytest.raises(ValueError):
            result.transition_to(LabResultStatus.PUBLISHED)

    def test_pending_cannot_go_to_doctor_review(self):
        result = make_lab_result(status=LabResultStatus.PENDING)
        with pytest.raises(ValueError):
            result.transition_to(LabResultStatus.DOCTOR_REVIEW)

    def test_can_transition_to_returns_false_for_invalid(self):
        result = make_lab_result(status=LabResultStatus.PENDING)
        assert result.can_transition_to(LabResultStatus.DOCTOR_REVIEW) is False


# ---------------------------------------------------------------------------
# apply_ai_draft
# ---------------------------------------------------------------------------


class TestApplyAiDraft:
    def test_apply_ai_draft_from_ai_processing(self):
        result = make_lab_result(status=LabResultStatus.AI_PROCESSING)
        result.apply_ai_draft(
            visual_findings={"opacity": True},
            draft_text="Mild opacity in left lung.",
            citations={"ref": "study_1"},
            confidence=0.92,
            model_versions={"vision": "v2.1"},
            processed_at=NOW,
        )
        assert result.status == LabResultStatus.AI_DRAFT
        assert result.ai_draft_text == "Mild opacity in left lung."
        assert result.ai_confidence == 0.92
        assert result.ai_visual_findings == {"opacity": True}
        assert result.ai_processed_at == NOW

    def test_apply_ai_draft_from_invalid_state_raises(self):
        result = make_lab_result(status=LabResultStatus.PENDING)
        with pytest.raises(ValueError):
            result.apply_ai_draft(
                visual_findings=None,
                draft_text="Report",
                citations=None,
                confidence=0.85,
                model_versions={},
                processed_at=NOW,
            )

    def test_apply_ai_draft_sets_all_fields(self):
        result = make_lab_result(status=LabResultStatus.AI_PROCESSING)
        result.apply_ai_draft(
            visual_findings={"finding": "normal"},
            draft_text="No abnormality detected.",
            citations={"pub": "journal_2024"},
            confidence=0.99,
            model_versions={"nlp": "v3", "vision": "v2"},
            processed_at=NOW,
        )
        assert result.ai_draft_citations == {"pub": "journal_2024"}
        assert result.ai_model_versions == {"nlp": "v3", "vision": "v2"}


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


class TestPublish:
    def test_publish_from_doctor_review(self):
        doctor_id = uuid.uuid4()
        result = make_lab_result(status=LabResultStatus.DOCTOR_REVIEW)
        result.ai_draft_text = "AI generated summary."

        result.publish(
            verified_by=doctor_id,
            verified_at=NOW,
            published_at=NOW,
        )

        assert result.status == LabResultStatus.PUBLISHED
        assert result.verified_by == doctor_id
        assert result.verified_at == NOW
        assert result.published_at == NOW
        assert result.published_text == "AI generated summary."  # falls back to ai_draft_text

    def test_publish_with_custom_text_overrides_ai_draft(self):
        result = make_lab_result(status=LabResultStatus.DOCTOR_REVIEW)
        result.ai_draft_text = "AI summary."

        result.publish(
            verified_by=uuid.uuid4(),
            verified_at=NOW,
            published_at=NOW,
            published_text="Doctor override text.",
        )

        assert result.published_text == "Doctor override text."

    def test_publish_from_invalid_state_raises(self):
        result = make_lab_result(status=LabResultStatus.AI_PROCESSING)
        with pytest.raises(ValueError, match="DOCTOR_REVIEW or NEEDS_MANUAL_REVIEW"):
            result.publish(
                verified_by=uuid.uuid4(),
                verified_at=NOW,
                published_at=NOW,
            )

    def test_publish_from_ai_draft_raises(self):
        result = make_lab_result(status=LabResultStatus.AI_DRAFT)
        with pytest.raises(ValueError):
            result.publish(
                verified_by=uuid.uuid4(),
                verified_at=NOW,
                published_at=NOW,
            )

    def test_publish_sets_doctor_notes(self):
        result = make_lab_result(status=LabResultStatus.NEEDS_MANUAL_REVIEW)
        result.publish(
            verified_by=uuid.uuid4(),
            verified_at=NOW,
            published_at=NOW,
            doctor_notes="Reviewed manually — normal findings.",
        )
        assert result.doctor_notes == "Reviewed manually — normal findings."

    def test_publish_with_published_findings(self):
        findings = {"key": "normal ECG pattern"}
        result = make_lab_result(status=LabResultStatus.DOCTOR_REVIEW)
        result.publish(
            verified_by=uuid.uuid4(),
            verified_at=NOW,
            published_at=NOW,
            published_findings=findings,
        )
        assert result.published_findings == findings
