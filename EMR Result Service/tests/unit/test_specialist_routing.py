"""Tests for the specialist reviewer routing feature.

Covered workflows
-----------------
1.  LabResult.claim()          — domain method (entity layer)
2.  _resolve_specialty()       — pure routing helper (use-case layer)
3.  UpdateAIDraftUseCase       — auto-assigns reviewer after AI finishes
4.  ClaimLabResultUseCase      — specialist claims an open-claim result
5.  VerifyAndPublishUseCase    — enforces reviewer_doctor_id check
6.  ListLabResultsUseCase      — specialty worklist filters
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from Application.dtos import UpdateAIDraftRequest, VerifyLabResultRequest
from Application.exceptions import (
    LabResultNotFoundError,
    ResultAlreadyClaimedError,
    ResultNotClaimableError,
    UnauthorizedReviewerError,
)
from Application.use_cases.claim_lab_result import ClaimLabResultUseCase
from Application.use_cases.get_lab_results import ListLabResultsUseCase
from Application.use_cases.update_ai_draft import UpdateAIDraftUseCase, _resolve_specialty
from Application.use_cases.verify_and_publish import VerifyAndPublishUseCase
from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.test_type import TestType
from tests.conftest import (
    FakeClinicalClient,
    FakeLabOrderRepo,
    FakeLabResultRepo,
    FakeNotificationClient,
    make_lab_order,
    make_lab_result,
)

NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ai_draft_request(**kwargs) -> UpdateAIDraftRequest:
    defaults = dict(
        ai_draft_text="Normal sinus rhythm.",
        ai_visual_findings={"finding": "normal"},
        ai_draft_citations={},
        ai_confidence=0.95,
        ai_model_versions={"model": "v1"},
    )
    defaults.update(kwargs)
    return UpdateAIDraftRequest(**defaults)


def _make_verify_request(**kwargs) -> VerifyLabResultRequest:
    defaults = dict(
        doctor_notes="Confirmed.",
        published_text="All normal.",
        published_findings=None,
    )
    defaults.update(kwargs)
    return VerifyLabResultRequest(**defaults)


# ---------------------------------------------------------------------------
# 1. Domain entity — LabResult.claim()
# ---------------------------------------------------------------------------


class TestLabResultClaimMethod:
    def test_claim_sets_reviewer_id(self):
        result = make_lab_result(status=LabResultStatus.DOCTOR_REVIEW)
        doctor = uuid.uuid4()
        result.claim(doctor)
        assert result.reviewer_doctor_id == doctor

    def test_claim_from_needs_manual_review(self):
        result = make_lab_result(status=LabResultStatus.NEEDS_MANUAL_REVIEW)
        doctor = uuid.uuid4()
        result.claim(doctor)
        assert result.reviewer_doctor_id == doctor

    def test_claim_already_claimed_raises(self):
        doctor_a = uuid.uuid4()
        doctor_b = uuid.uuid4()
        result = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            reviewer_doctor_id=doctor_a,
        )
        with pytest.raises(ValueError, match="already been claimed"):
            result.claim(doctor_b)

    def test_claim_wrong_status_pending_raises(self):
        result = make_lab_result(status=LabResultStatus.PENDING)
        with pytest.raises(ValueError):
            result.claim(uuid.uuid4())

    def test_claim_wrong_status_published_raises(self):
        result = make_lab_result(status=LabResultStatus.PUBLISHED)
        with pytest.raises(ValueError):
            result.claim(uuid.uuid4())

    def test_claim_wrong_status_ai_processing_raises(self):
        result = make_lab_result(status=LabResultStatus.AI_PROCESSING)
        with pytest.raises(ValueError):
            result.claim(uuid.uuid4())


# ---------------------------------------------------------------------------
# 2. _resolve_specialty helper
# ---------------------------------------------------------------------------


class TestResolveSpecialty:
    def test_blood_panel_is_general(self):
        assert _resolve_specialty(None, TestType.BLOOD_PANEL) is None

    def test_urine_is_general(self):
        assert _resolve_specialty(None, TestType.URINE) is None

    def test_ecg_implies_cardiology(self):
        assert _resolve_specialty(None, TestType.ECG) == "cardiology"

    def test_imaging_implies_radiology(self):
        assert _resolve_specialty(None, TestType.IMAGING) == "radiology"

    def test_chest_xray_implies_radiology(self):
        assert _resolve_specialty(None, TestType.CHEST_XRAY) == "radiology"

    def test_bone_xray_implies_radiology(self):
        assert _resolve_specialty(None, TestType.BONE_XRAY) == "radiology"

    def test_abdominal_xray_implies_radiology(self):
        assert _resolve_specialty(None, TestType.ABDOMINAL_XRAY) == "radiology"

    def test_skull_xray_implies_radiology(self):
        assert _resolve_specialty(None, TestType.SKULL_XRAY) == "radiology"

    def test_spine_xray_implies_radiology(self):
        assert _resolve_specialty(None, TestType.SPINE_XRAY) == "radiology"

    def test_radiology_department_overrides_test_type(self):
        # Even a blood panel in the radiology dept routes to radiology
        assert _resolve_specialty("radiology", TestType.BLOOD_PANEL) == "radiology"

    def test_cardiology_department_no_test_type(self):
        assert _resolve_specialty("cardiology", None) == "cardiology"

    def test_neurology_department(self):
        assert _resolve_specialty("neurology", None) == "neurology"

    def test_unknown_department_and_general_test_returns_none(self):
        assert _resolve_specialty("general_medicine", TestType.BLOOD_PANEL) is None

    def test_both_none_returns_none(self):
        assert _resolve_specialty(None, None) is None


# ---------------------------------------------------------------------------
# 3. UpdateAIDraftUseCase — reviewer routing
# ---------------------------------------------------------------------------


class TestUpdateAIDraftRouting:
    @pytest.fixture
    def order_repo(self) -> FakeLabOrderRepo:
        return FakeLabOrderRepo()

    @pytest.fixture
    def result_repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    def _uc(self, result_repo, order_repo) -> UpdateAIDraftUseCase:
        return UpdateAIDraftUseCase(result_repo, order_repo)

    async def test_general_test_assigns_gp_as_reviewer(self, result_repo, order_repo):
        gp_id = uuid.uuid4()
        order = make_lab_order(doctor_id=gp_id, test_type=TestType.BLOOD_PANEL)
        result = make_lab_result(
            order_id=order.id,
            doctor_id=gp_id,
            status=LabResultStatus.PENDING,
        )
        await order_repo.save(order)
        await result_repo.save(result)

        resp = await self._uc(result_repo, order_repo).execute(result.id, _make_ai_draft_request())

        saved = await result_repo.get_by_id(result.id)
        assert saved.reviewer_doctor_id == gp_id
        assert saved.required_specialty is None
        assert saved.status == LabResultStatus.DOCTOR_REVIEW

    async def test_ecg_routes_to_cardiology_open_claim(self, result_repo, order_repo):
        gp_id = uuid.uuid4()
        order = make_lab_order(doctor_id=gp_id, test_type=TestType.ECG)
        result = make_lab_result(order_id=order.id, doctor_id=gp_id, status=LabResultStatus.PENDING)
        await order_repo.save(order)
        await result_repo.save(result)

        await self._uc(result_repo, order_repo).execute(result.id, _make_ai_draft_request())

        saved = await result_repo.get_by_id(result.id)
        assert saved.reviewer_doctor_id is None   # open claim
        assert saved.required_specialty == "cardiology"
        assert saved.status == LabResultStatus.DOCTOR_REVIEW

    async def test_chest_xray_routes_to_radiology_open_claim(self, result_repo, order_repo):
        gp_id = uuid.uuid4()
        order = make_lab_order(doctor_id=gp_id, test_type=TestType.CHEST_XRAY)
        result = make_lab_result(order_id=order.id, doctor_id=gp_id, status=LabResultStatus.PENDING)
        await order_repo.save(order)
        await result_repo.save(result)

        await self._uc(result_repo, order_repo).execute(result.id, _make_ai_draft_request())

        saved = await result_repo.get_by_id(result.id)
        assert saved.reviewer_doctor_id is None
        assert saved.required_specialty == "radiology"

    async def test_radiology_department_routes_to_radiology(self, result_repo, order_repo):
        gp_id = uuid.uuid4()
        order = make_lab_order(doctor_id=gp_id, test_type=TestType.BLOOD_PANEL, department="radiology")
        result = make_lab_result(order_id=order.id, doctor_id=gp_id, status=LabResultStatus.PENDING)
        await order_repo.save(order)
        await result_repo.save(result)

        await self._uc(result_repo, order_repo).execute(result.id, _make_ai_draft_request())

        saved = await result_repo.get_by_id(result.id)
        assert saved.reviewer_doctor_id is None
        assert saved.required_specialty == "radiology"

    async def test_routing_is_idempotent_when_already_assigned(self, result_repo, order_repo):
        """Celery retry: if reviewer already set, must not overwrite."""
        existing_reviewer = uuid.uuid4()
        gp_id = uuid.uuid4()
        order = make_lab_order(doctor_id=gp_id, test_type=TestType.ECG)
        result = make_lab_result(
            order_id=order.id,
            doctor_id=gp_id,
            status=LabResultStatus.AI_PROCESSING,
            reviewer_doctor_id=existing_reviewer,
            required_specialty="cardiology",
        )
        await order_repo.save(order)
        await result_repo.save(result)

        await self._uc(result_repo, order_repo).execute(result.id, _make_ai_draft_request())

        saved = await result_repo.get_by_id(result.id)
        # Must not be overwritten
        assert saved.reviewer_doctor_id == existing_reviewer
        assert saved.required_specialty == "cardiology"

    async def test_missing_order_gracefully_skips_routing(self, result_repo, order_repo):
        """No order in repo → routing skipped, result still advances."""
        result = make_lab_result(status=LabResultStatus.PENDING)
        await result_repo.save(result)

        await self._uc(result_repo, order_repo).execute(result.id, _make_ai_draft_request())

        saved = await result_repo.get_by_id(result.id)
        assert saved.status == LabResultStatus.DOCTOR_REVIEW
        assert saved.reviewer_doctor_id is None
        assert saved.required_specialty is None

    async def test_result_not_found_raises(self, result_repo, order_repo):
        with pytest.raises(LabResultNotFoundError):
            await self._uc(result_repo, order_repo).execute(uuid.uuid4(), _make_ai_draft_request())

    async def test_wrong_status_raises(self, result_repo, order_repo):
        result = make_lab_result(status=LabResultStatus.PUBLISHED)
        await result_repo.save(result)
        with pytest.raises(ValueError):
            await self._uc(result_repo, order_repo).execute(result.id, _make_ai_draft_request())


# ---------------------------------------------------------------------------
# 4. ClaimLabResultUseCase
# ---------------------------------------------------------------------------


class TestClaimLabResultUseCase:
    @pytest.fixture
    def result_repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    def _uc(self, result_repo) -> ClaimLabResultUseCase:
        return ClaimLabResultUseCase(result_repo)

    async def test_specialist_claims_open_result(self, result_repo):
        specialist = uuid.uuid4()
        result = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="radiology",
            reviewer_doctor_id=None,
        )
        await result_repo.save(result)

        resp = await self._uc(result_repo).execute(result.id, specialist)

        assert resp.reviewer_doctor_id == specialist
        saved = await result_repo.get_by_id(result.id)
        assert saved.reviewer_doctor_id == specialist

    async def test_specialist_claims_needs_manual_review(self, result_repo):
        specialist = uuid.uuid4()
        result = make_lab_result(
            status=LabResultStatus.NEEDS_MANUAL_REVIEW,
            required_specialty="cardiology",
            reviewer_doctor_id=None,
        )
        await result_repo.save(result)

        resp = await self._uc(result_repo).execute(result.id, specialist)
        assert resp.reviewer_doctor_id == specialist

    async def test_claim_already_taken_raises(self, result_repo):
        first_claimer = uuid.uuid4()
        second_claimer = uuid.uuid4()
        result = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="radiology",
            reviewer_doctor_id=first_claimer,  # already claimed
        )
        await result_repo.save(result)

        with pytest.raises(ResultAlreadyClaimedError):
            await self._uc(result_repo).execute(result.id, second_claimer)

    async def test_general_test_not_claimable(self, result_repo):
        result = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty=None,  # general test
        )
        await result_repo.save(result)

        with pytest.raises(ResultNotClaimableError):
            await self._uc(result_repo).execute(result.id, uuid.uuid4())

    async def test_wrong_status_not_claimable(self, result_repo):
        for bad_status in (LabResultStatus.PENDING, LabResultStatus.AI_PROCESSING, LabResultStatus.PUBLISHED):
            result = make_lab_result(
                status=bad_status,
                required_specialty="radiology",
                reviewer_doctor_id=None,
            )
            await result_repo.save(result)
            with pytest.raises(ResultNotClaimableError):
                await self._uc(result_repo).execute(result.id, uuid.uuid4())

    async def test_result_not_found_raises(self, result_repo):
        with pytest.raises(LabResultNotFoundError):
            await self._uc(result_repo).execute(uuid.uuid4(), uuid.uuid4())


# ---------------------------------------------------------------------------
# 5. VerifyAndPublishUseCase — reviewer enforcement
# ---------------------------------------------------------------------------


class TestVerifyReviewerEnforcement:
    """Tests specifically for the reviewer_doctor_id guard introduced in this feature."""

    @pytest.fixture
    def order_repo(self) -> FakeLabOrderRepo:
        return FakeLabOrderRepo()

    @pytest.fixture
    def result_repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    @pytest.fixture
    def notif_client(self) -> FakeNotificationClient:
        return FakeNotificationClient()

    @pytest.fixture
    def clinical_client(self) -> FakeClinicalClient:
        return FakeClinicalClient()

    def _uc(self, result_repo, order_repo, notif_client, clinical_client) -> VerifyAndPublishUseCase:
        return VerifyAndPublishUseCase(
            result_repo=result_repo,
            order_repo=order_repo,
            notification_client=notif_client,
            clinical_client=clinical_client,
        )

    async def _setup_claimed_result(self, result_repo, order_repo, *, reviewer_id: uuid.UUID):
        """Helper: create order + DOCTOR_REVIEW result with an assigned reviewer."""
        order = make_lab_order()
        await order_repo.save(order)
        result = make_lab_result(
            order_id=order.id,
            status=LabResultStatus.DOCTOR_REVIEW,
            reviewer_doctor_id=reviewer_id,
        )
        await result_repo.save(result)
        return result

    async def test_assigned_reviewer_can_verify(
        self, result_repo, order_repo, notif_client, clinical_client
    ):
        reviewer = uuid.uuid4()
        result = await self._setup_claimed_result(result_repo, order_repo, reviewer_id=reviewer)

        resp = await self._uc(result_repo, order_repo, notif_client, clinical_client).execute(
            result_id=result.id,
            doctor_id=reviewer,
            request=_make_verify_request(),
            caller_role="doctor",
        )
        assert resp.status == LabResultStatus.PUBLISHED

    async def test_wrong_doctor_cannot_verify(
        self, result_repo, order_repo, notif_client, clinical_client
    ):
        reviewer = uuid.uuid4()
        intruder = uuid.uuid4()
        result = await self._setup_claimed_result(result_repo, order_repo, reviewer_id=reviewer)

        with pytest.raises(UnauthorizedReviewerError):
            await self._uc(result_repo, order_repo, notif_client, clinical_client).execute(
                result_id=result.id,
                doctor_id=intruder,
                request=_make_verify_request(),
                caller_role="doctor",
            )

    async def test_admin_bypasses_reviewer_check(
        self, result_repo, order_repo, notif_client, clinical_client
    ):
        reviewer = uuid.uuid4()
        admin = uuid.uuid4()
        result = await self._setup_claimed_result(result_repo, order_repo, reviewer_id=reviewer)

        # admin is a different user but caller_role="admin" bypasses the check
        resp = await self._uc(result_repo, order_repo, notif_client, clinical_client).execute(
            result_id=result.id,
            doctor_id=admin,
            request=_make_verify_request(),
            caller_role="admin",
        )
        assert resp.status == LabResultStatus.PUBLISHED

    async def test_no_reviewer_assigned_any_doctor_can_verify(
        self, result_repo, order_repo, notif_client, clinical_client
    ):
        """reviewer_doctor_id=None means the result is open — any doctor can verify."""
        any_doctor = uuid.uuid4()
        order = make_lab_order()
        await order_repo.save(order)
        result = make_lab_result(
            order_id=order.id,
            status=LabResultStatus.DOCTOR_REVIEW,
            reviewer_doctor_id=None,  # open / general test
        )
        await result_repo.save(result)

        resp = await self._uc(result_repo, order_repo, notif_client, clinical_client).execute(
            result_id=result.id,
            doctor_id=any_doctor,
            request=_make_verify_request(),
            caller_role="doctor",
        )
        assert resp.status == LabResultStatus.PUBLISHED

    async def test_result_not_found_raises(
        self, result_repo, order_repo, notif_client, clinical_client
    ):
        with pytest.raises(LabResultNotFoundError):
            await self._uc(result_repo, order_repo, notif_client, clinical_client).execute(
                result_id=uuid.uuid4(),
                doctor_id=uuid.uuid4(),
                request=_make_verify_request(),
                caller_role="doctor",
            )


# ---------------------------------------------------------------------------
# 6. ListLabResultsUseCase — specialty worklist filters
# ---------------------------------------------------------------------------


class TestListLabResultsWorklist:
    @pytest.fixture
    def result_repo(self) -> FakeLabResultRepo:
        return FakeLabResultRepo()

    def _uc(self, result_repo) -> ListLabResultsUseCase:
        return ListLabResultsUseCase(result_repo)

    async def test_open_claim_filter_returns_only_unclaimed_specialty(self, result_repo):
        radiologist_claimer = uuid.uuid4()
        # unclaimed radiology
        unclaimed = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="radiology",
            reviewer_doctor_id=None,
        )
        # claimed radiology (already taken)
        claimed = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="radiology",
            reviewer_doctor_id=radiologist_claimer,
        )
        # general test (no specialty)
        general = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            reviewer_doctor_id=uuid.uuid4(),
        )
        for r in [unclaimed, claimed, general]:
            await result_repo.save(r)

        results = await self._uc(result_repo).execute(caller_role="doctor", open_claim=True)

        ids = {r.id for r in results}
        assert unclaimed.id in ids
        assert claimed.id not in ids
        assert general.id not in ids

    async def test_required_specialty_filter(self, result_repo):
        rad = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="radiology",
        )
        card = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="cardiology",
        )
        general = make_lab_result(status=LabResultStatus.DOCTOR_REVIEW)
        for r in [rad, card, general]:
            await result_repo.save(r)

        results = await self._uc(result_repo).execute(
            caller_role="doctor", required_specialty="radiology"
        )
        ids = {r.id for r in results}
        assert rad.id in ids
        assert card.id not in ids
        assert general.id not in ids

    async def test_reviewer_doctor_id_filter(self, result_repo):
        specialist = uuid.uuid4()
        mine = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="cardiology",
            reviewer_doctor_id=specialist,
        )
        other = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="cardiology",
            reviewer_doctor_id=uuid.uuid4(),
        )
        for r in [mine, other]:
            await result_repo.save(r)

        results = await self._uc(result_repo).execute(
            caller_role="doctor", reviewer_doctor_id=specialist
        )
        ids = {r.id for r in results}
        assert mine.id in ids
        assert other.id not in ids

    async def test_combined_specialty_and_open_claim(self, result_repo):
        unclaimed_rad = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="radiology",
            reviewer_doctor_id=None,
        )
        unclaimed_card = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="cardiology",
            reviewer_doctor_id=None,
        )
        claimed_rad = make_lab_result(
            status=LabResultStatus.DOCTOR_REVIEW,
            required_specialty="radiology",
            reviewer_doctor_id=uuid.uuid4(),
        )
        for r in [unclaimed_rad, unclaimed_card, claimed_rad]:
            await result_repo.save(r)

        results = await self._uc(result_repo).execute(
            caller_role="doctor",
            required_specialty="radiology",
            open_claim=True,
        )
        ids = {r.id for r in results}
        assert unclaimed_rad.id in ids
        assert unclaimed_card.id not in ids
        assert claimed_rad.id not in ids

    async def test_patient_only_sees_published(self, result_repo):
        """Regression: specialty worklist must not leak unpublished results to patients."""
        patient_id = uuid.uuid4()
        draft = make_lab_result(
            patient_id=patient_id,
            status=LabResultStatus.DOCTOR_REVIEW,
        )
        published = make_lab_result(
            patient_id=patient_id,
            status=LabResultStatus.PUBLISHED,
        )
        for r in [draft, published]:
            await result_repo.save(r)

        results = await self._uc(result_repo).execute(
            caller_role="patient", patient_id=patient_id
        )
        ids = {r.id for r in results}
        assert draft.id not in ids
        assert published.id in ids


# ---------------------------------------------------------------------------
# 7. End-to-end: full specialty routing pipeline
# ---------------------------------------------------------------------------


class TestFullSpecialtyPipeline:
    """Integration-style test running through the complete specialist flow:
    upload → AI draft → open claim → specialist claims → specialist verifies.
    """

    @pytest.fixture
    def repos(self):
        return FakeLabOrderRepo(), FakeLabResultRepo()

    @pytest.fixture
    def external(self):
        return FakeNotificationClient(), FakeClinicalClient()

    async def test_radiology_end_to_end(self, repos, external):
        order_repo, result_repo = repos
        notif, clinical = external

        gp_id = uuid.uuid4()
        radiologist_id = uuid.uuid4()

        # 1. GP orders a chest X-ray
        order = make_lab_order(doctor_id=gp_id, test_type=TestType.CHEST_XRAY)
        await order_repo.save(order)
        result = make_lab_result(
            order_id=order.id, doctor_id=gp_id, status=LabResultStatus.PENDING
        )
        await result_repo.save(result)

        # 2. AI processes it → should route to radiology (open claim)
        ai_uc = UpdateAIDraftUseCase(result_repo, order_repo)
        await ai_uc.execute(result.id, _make_ai_draft_request())

        after_ai = await result_repo.get_by_id(result.id)
        assert after_ai.status == LabResultStatus.DOCTOR_REVIEW
        assert after_ai.required_specialty == "radiology"
        assert after_ai.reviewer_doctor_id is None  # open

        # 3. Radiologist queries the worklist and claims the result
        worklist = await ListLabResultsUseCase(result_repo).execute(
            caller_role="doctor",
            required_specialty="radiology",
            open_claim=True,
        )
        assert any(r.id == result.id for r in worklist)

        claim_uc = ClaimLabResultUseCase(result_repo)
        await claim_uc.execute(result.id, radiologist_id)

        after_claim = await result_repo.get_by_id(result.id)
        assert after_claim.reviewer_doctor_id == radiologist_id

        # 4. GP attempts to verify — must be rejected
        verify_uc = VerifyAndPublishUseCase(result_repo, order_repo, notif, clinical)
        with pytest.raises(UnauthorizedReviewerError):
            await verify_uc.execute(
                result_id=result.id,
                doctor_id=gp_id,
                request=_make_verify_request(),
                caller_role="doctor",
            )

        # 5. Radiologist verifies — should succeed
        resp = await verify_uc.execute(
            result_id=result.id,
            doctor_id=radiologist_id,
            request=_make_verify_request(),
            caller_role="doctor",
        )
        assert resp.status == LabResultStatus.PUBLISHED

        # 6. Result no longer on open-claim worklist
        worklist_after = await ListLabResultsUseCase(result_repo).execute(
            caller_role="doctor",
            required_specialty="radiology",
            open_claim=True,
        )
        assert not any(r.id == result.id for r in worklist_after)

    async def test_general_blood_test_gp_reviews_directly(self, repos, external):
        order_repo, result_repo = repos
        notif, clinical = external

        gp_id = uuid.uuid4()
        order = make_lab_order(doctor_id=gp_id, test_type=TestType.BLOOD_PANEL)
        await order_repo.save(order)
        result = make_lab_result(
            order_id=order.id, doctor_id=gp_id, status=LabResultStatus.PENDING
        )
        await result_repo.save(result)

        # AI processes it → GP is auto-assigned
        ai_uc = UpdateAIDraftUseCase(result_repo, order_repo)
        await ai_uc.execute(result.id, _make_ai_draft_request())

        after_ai = await result_repo.get_by_id(result.id)
        assert after_ai.reviewer_doctor_id == gp_id
        assert after_ai.required_specialty is None

        # GP verifies directly (no claim step needed)
        verify_uc = VerifyAndPublishUseCase(result_repo, order_repo, notif, clinical)
        resp = await verify_uc.execute(
            result_id=result.id,
            doctor_id=gp_id,
            request=_make_verify_request(),
            caller_role="doctor",
        )
        assert resp.status == LabResultStatus.PUBLISHED
