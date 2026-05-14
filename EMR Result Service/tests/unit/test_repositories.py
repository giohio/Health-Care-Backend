"""Unit tests for LabOrderRepository and LabResultRepository.

All DB interactions are mocked using AsyncMock so no real database is needed.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from Domain.entities.lab_order import LabOrder
from Domain.entities.lab_result import LabResult
from Domain.value_objects.lab_result_status import LabResultStatus
from Domain.value_objects.order_priority import OrderPriority
from Domain.value_objects.test_type import TestType
from infrastructure.repositories.lab_order_repository import LabOrderRepository
from infrastructure.repositories.lab_result_repository import LabResultRepository

NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

ORDER_ID = uuid.uuid4()
PATIENT_ID = uuid.uuid4()
DOCTOR_ID = uuid.uuid4()
RESULT_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Helpers to build fake ORM model objects (plain MagicMock with attrs)
# ---------------------------------------------------------------------------

def make_order_model(**overrides) -> MagicMock:
    model = MagicMock()
    model.id = overrides.get("id", ORDER_ID)
    model.patient_id = overrides.get("patient_id", PATIENT_ID)
    model.doctor_id = overrides.get("doctor_id", DOCTOR_ID)
    model.appointment_id = overrides.get("appointment_id", None)
    model.test_name = overrides.get("test_name", "Complete Blood Count")
    model.test_type = overrides.get("test_type", TestType.BLOOD_PANEL)
    model.department = overrides.get("department", None)
    model.instructions = overrides.get("instructions", None)
    model.priority = overrides.get("priority", OrderPriority.ROUTINE)
    model.ordered_at = overrides.get("ordered_at", NOW)
    model.created_at = overrides.get("created_at", NOW)
    return model


def make_result_model(**overrides) -> MagicMock:
    model = MagicMock()
    model.id = overrides.get("id", RESULT_ID)
    model.order_id = overrides.get("order_id", ORDER_ID)
    model.patient_id = overrides.get("patient_id", PATIENT_ID)
    model.doctor_id = overrides.get("doctor_id", DOCTOR_ID)
    model.status = overrides.get("status", LabResultStatus.PENDING)
    model.file_url = overrides.get("file_url", "s3://bucket/result.pdf")
    model.file_type = overrides.get("file_type", "pdf")
    model.ai_visual_findings = overrides.get("ai_visual_findings", None)
    model.ai_draft_text = overrides.get("ai_draft_text", None)
    model.ai_draft_citations = overrides.get("ai_draft_citations", None)
    model.ai_confidence = overrides.get("ai_confidence", None)
    model.ai_model_versions = overrides.get("ai_model_versions", None)
    model.ai_processed_at = overrides.get("ai_processed_at", None)
    model.doctor_notes = overrides.get("doctor_notes", None)
    model.verified_by = overrides.get("verified_by", None)
    model.verified_at = overrides.get("verified_at", None)
    model.published_text = overrides.get("published_text", None)
    model.published_findings = overrides.get("published_findings", None)
    model.published_at = overrides.get("published_at", None)
    model.created_at = overrides.get("created_at", NOW)
    return model


def make_async_session() -> AsyncMock:
    """Build a minimal AsyncSession mock."""
    session = AsyncMock()
    session.add = MagicMock()  # synchronous add
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def make_execute_result(scalar=None, scalars_list=None):
    """Return a mock that mimics SQLAlchemy's execute() result."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = scalars_list or []
    result.scalars.return_value = scalars_mock
    return result


# ---------------------------------------------------------------------------
# LabOrderRepository — _to_entity
# ---------------------------------------------------------------------------

class TestLabOrderRepositoryToEntity:
    def test_maps_all_fields(self):
        model = make_order_model()
        entity = LabOrderRepository._to_entity(model)
        assert entity.id == model.id
        assert entity.patient_id == model.patient_id
        assert entity.doctor_id == model.doctor_id
        assert entity.test_name == model.test_name
        assert entity.test_type == model.test_type
        assert entity.priority == model.priority
        assert entity.ordered_at == model.ordered_at

    def test_optional_fields_none(self):
        model = make_order_model(appointment_id=None, department=None, instructions=None)
        entity = LabOrderRepository._to_entity(model)
        assert entity.appointment_id is None
        assert entity.department is None
        assert entity.instructions is None


# ---------------------------------------------------------------------------
# LabOrderRepository — async methods
# ---------------------------------------------------------------------------

class TestLabOrderRepositorySave:
    @pytest.mark.asyncio
    async def test_save_calls_add_flush_refresh(self):
        session = make_async_session()
        model = make_order_model()
        session.execute.return_value = make_execute_result(scalar=None)
        session.refresh.side_effect = lambda m: None  # refresh sets no attrs on mock

        repo = LabOrderRepository(session)
        order = LabOrder(
            id=ORDER_ID,
            patient_id=PATIENT_ID,
            doctor_id=DOCTOR_ID,
            test_name="CBC",
            priority=OrderPriority.ROUTINE,
        )

        # After refresh, _to_entity will be called on the LabOrderModel stub.
        # We patch session.refresh to set the expected attrs on whatever model was added.
        added_models = []
        def capture_add(m):
            added_models.append(m)

        session.add.side_effect = capture_add

        async def do_refresh(m):
            # simulate what DB would set
            m.ordered_at = NOW
            m.created_at = NOW
        session.refresh.side_effect = do_refresh

        result = await repo.save(order)
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once()
        assert result.id == ORDER_ID
        assert result.test_name == "CBC"


class TestLabOrderRepositoryGetById:
    @pytest.mark.asyncio
    async def test_returns_entity_when_found(self):
        session = make_async_session()
        model = make_order_model()
        session.execute.return_value = make_execute_result(scalar=model)

        repo = LabOrderRepository(session)
        entity = await repo.get_by_id(ORDER_ID)
        assert entity is not None
        assert entity.id == ORDER_ID

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = make_async_session()
        session.execute.return_value = make_execute_result(scalar=None)

        repo = LabOrderRepository(session)
        entity = await repo.get_by_id(uuid.uuid4())
        assert entity is None


class TestLabOrderRepositoryList:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        session = make_async_session()
        session.execute.return_value = make_execute_result(scalars_list=[])

        repo = LabOrderRepository(session)
        results = await repo.list()
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_mapped_entities(self):
        session = make_async_session()
        model1 = make_order_model(id=uuid.uuid4(), test_name="CBC")
        model2 = make_order_model(id=uuid.uuid4(), test_name="X-Ray")
        session.execute.return_value = make_execute_result(scalars_list=[model1, model2])

        repo = LabOrderRepository(session)
        results = await repo.list()
        assert len(results) == 2
        names = {r.test_name for r in results}
        assert names == {"CBC", "X-Ray"}

    @pytest.mark.asyncio
    async def test_list_with_patient_filter(self):
        session = make_async_session()
        pid = uuid.uuid4()
        model = make_order_model(patient_id=pid)
        session.execute.return_value = make_execute_result(scalars_list=[model])

        repo = LabOrderRepository(session)
        results = await repo.list(patient_id=pid)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_with_doctor_filter(self):
        session = make_async_session()
        did = uuid.uuid4()
        model = make_order_model(doctor_id=did)
        session.execute.return_value = make_execute_result(scalars_list=[model])

        repo = LabOrderRepository(session)
        results = await repo.list(doctor_id=did)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# LabResultRepository — _to_entity
# ---------------------------------------------------------------------------

class TestLabResultRepositoryToEntity:
    def test_maps_all_fields(self):
        model = make_result_model()
        entity = LabResultRepository._to_entity(model)
        assert entity.id == model.id
        assert entity.order_id == model.order_id
        assert entity.patient_id == model.patient_id
        assert entity.doctor_id == model.doctor_id
        assert entity.status == model.status
        assert entity.file_url == model.file_url
        assert entity.file_type == model.file_type

    def test_optional_ai_fields_none(self):
        model = make_result_model(
            ai_visual_findings=None,
            ai_draft_text=None,
            ai_confidence=None,
        )
        entity = LabResultRepository._to_entity(model)
        assert entity.ai_visual_findings is None
        assert entity.ai_draft_text is None
        assert entity.ai_confidence is None

    def test_published_fields_mapped(self):
        model = make_result_model(
            status=LabResultStatus.PUBLISHED,
            published_text="All normal.",
            published_at=NOW,
            verified_by=DOCTOR_ID,
            verified_at=NOW,
        )
        entity = LabResultRepository._to_entity(model)
        assert entity.published_text == "All normal."
        assert entity.published_at == NOW


# ---------------------------------------------------------------------------
# LabResultRepository — save (insert path)
# ---------------------------------------------------------------------------

class TestLabResultRepositorySaveInsert:
    @pytest.mark.asyncio
    async def test_insert_when_not_existing(self):
        session = make_async_session()
        # No existing model found
        session.execute.return_value = make_execute_result(scalar=None)

        captured_model = []

        def capture_add(m):
            captured_model.append(m)

        session.add.side_effect = capture_add

        async def do_refresh(m):
            # Simulate DB returning the result with created_at set
            m.created_at = NOW
            m.status = LabResultStatus.PENDING

        session.refresh.side_effect = do_refresh

        repo = LabResultRepository(session)
        result = LabResult(
            id=RESULT_ID,
            order_id=ORDER_ID,
            patient_id=PATIENT_ID,
            doctor_id=DOCTOR_ID,
            status=LabResultStatus.PENDING,
        )

        saved = await repo.save(result)
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once()
        assert saved is not None


# ---------------------------------------------------------------------------
# LabResultRepository — save (update path)
# ---------------------------------------------------------------------------

class TestLabResultRepositorySaveUpdate:
    @pytest.mark.asyncio
    async def test_update_when_existing(self):
        session = make_async_session()
        existing_model = make_result_model(status=LabResultStatus.PENDING)
        session.execute.return_value = make_execute_result(scalar=existing_model)

        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        repo = LabResultRepository(session)
        result = LabResult(
            id=RESULT_ID,
            order_id=ORDER_ID,
            patient_id=PATIENT_ID,
            doctor_id=DOCTOR_ID,
            status=LabResultStatus.AI_PROCESSING,
            file_url="s3://bucket/r.pdf",
            file_type="pdf",
            ai_draft_text="Some findings.",
        )

        await repo.save(result)
        # Should NOT call add (update path)
        session.add.assert_not_called()
        session.flush.assert_awaited_once()
        # Existing model fields should be updated
        assert existing_model.status == LabResultStatus.AI_PROCESSING
        assert existing_model.ai_draft_text == "Some findings."


# ---------------------------------------------------------------------------
# LabResultRepository — get_by_id
# ---------------------------------------------------------------------------

class TestLabResultRepositoryGetById:
    @pytest.mark.asyncio
    async def test_returns_entity_when_found(self):
        session = make_async_session()
        model = make_result_model()
        session.execute.return_value = make_execute_result(scalar=model)

        repo = LabResultRepository(session)
        entity = await repo.get_by_id(RESULT_ID)
        assert entity is not None
        assert entity.id == RESULT_ID

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = make_async_session()
        session.execute.return_value = make_execute_result(scalar=None)

        repo = LabResultRepository(session)
        entity = await repo.get_by_id(uuid.uuid4())
        assert entity is None


# ---------------------------------------------------------------------------
# LabResultRepository — list
# ---------------------------------------------------------------------------

class TestLabResultRepositoryList:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        session = make_async_session()
        session.execute.return_value = make_execute_result(scalars_list=[])

        repo = LabResultRepository(session)
        results = await repo.list()
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_all_mapped_entities(self):
        session = make_async_session()
        m1 = make_result_model(id=uuid.uuid4(), status=LabResultStatus.PENDING)
        m2 = make_result_model(id=uuid.uuid4(), status=LabResultStatus.PUBLISHED)
        session.execute.return_value = make_execute_result(scalars_list=[m1, m2])

        repo = LabResultRepository(session)
        results = await repo.list()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_with_patient_filter(self):
        session = make_async_session()
        pid = uuid.uuid4()
        model = make_result_model(patient_id=pid)
        session.execute.return_value = make_execute_result(scalars_list=[model])

        repo = LabResultRepository(session)
        results = await repo.list(patient_id=pid)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_with_doctor_filter(self):
        session = make_async_session()
        did = uuid.uuid4()
        model = make_result_model(doctor_id=did)
        session.execute.return_value = make_execute_result(scalars_list=[model])

        repo = LabResultRepository(session)
        results = await repo.list(doctor_id=did)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self):
        session = make_async_session()
        model = make_result_model(status=LabResultStatus.PUBLISHED)
        session.execute.return_value = make_execute_result(scalars_list=[model])

        repo = LabResultRepository(session)
        results = await repo.list(status=LabResultStatus.PUBLISHED)
        assert len(results) == 1
        assert results[0].status == LabResultStatus.PUBLISHED
