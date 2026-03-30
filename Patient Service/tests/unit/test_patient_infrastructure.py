import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from infrastructure.database import session as session_module


@pytest.mark.asyncio
async def test_get_db_commit_and_rollback(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        async def commit(self):
            await asyncio.sleep(0)
            self.commits += 1

        async def rollback(self):
            await asyncio.sleep(0)
            self.rollbacks += 1

    db = FakeSession()

    class Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(session_module, "AsyncSessionLocal", Factory())

    agen = session_module.get_db()
    assert await anext(agen) is db
    with pytest.raises(StopAsyncIteration):
        await anext(agen)
    assert db.commits == 1

    agen2 = session_module.get_db()
    await anext(agen2)
    with pytest.raises(RuntimeError):
        await agen2.athrow(RuntimeError("x"))
    assert db.rollbacks == 1


# ──────────────────────────────────────────────
# OutboxEventPublisher
# ──────────────────────────────────────────────

def _make_session():
    return AsyncMock()


class TestOutboxEventPublisher:
    @pytest.mark.asyncio
    async def test_publish_with_user_id(self):
        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        import infrastructure.publishers.outbox_event_publisher as pub_module

        calls = []

        async def fake_write(session, *, aggregate_id, aggregate_type, event_type, payload):
            calls.append({"aggregate_id": aggregate_id, "aggregate_type": aggregate_type})

        with patch.object(pub_module.OutboxWriter, "write", side_effect=fake_write):
            user_id = str(uuid.uuid4())
            pub = OutboxEventPublisher(_make_session())
            await pub.publish("exchange", "routing_key", {"user_id": user_id})

        assert len(calls) == 1
        assert str(calls[0]["aggregate_id"]) == user_id
        assert calls[0]["aggregate_type"] == "exchange"

    @pytest.mark.asyncio
    async def test_publish_with_id_field(self):
        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        import infrastructure.publishers.outbox_event_publisher as pub_module

        calls = []

        async def fake_write(session, *, aggregate_id, aggregate_type, event_type, payload):
            calls.append({"aggregate_id": aggregate_id})

        with patch.object(pub_module.OutboxWriter, "write", side_effect=fake_write):
            id_val = str(uuid.uuid4())
            pub = OutboxEventPublisher(_make_session())
            await pub.publish("exchange", "routing_key", {"id": id_val})

        assert str(calls[0]["aggregate_id"]) == id_val

    @pytest.mark.asyncio
    async def test_publish_with_invalid_uuid_uses_random(self):
        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        import infrastructure.publishers.outbox_event_publisher as pub_module

        calls = []

        async def fake_write(session, *, aggregate_id, aggregate_type, event_type, payload):
            calls.append({"aggregate_id": aggregate_id})

        with patch.object(pub_module.OutboxWriter, "write", side_effect=fake_write):
            pub = OutboxEventPublisher(_make_session())
            await pub.publish("exchange", "routing_key", {"user_id": "not-a-uuid"})

        # Should still produce a valid UUID (randomly generated fallback)
        assert isinstance(calls[0]["aggregate_id"], uuid.UUID)

    @pytest.mark.asyncio
    async def test_publish_without_ids_uses_random(self):
        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        import infrastructure.publishers.outbox_event_publisher as pub_module

        calls = []

        async def fake_write(session, *, aggregate_id, aggregate_type, event_type, payload):
            calls.append({"aggregate_id": aggregate_id})

        with patch.object(pub_module.OutboxWriter, "write", side_effect=fake_write):
            pub = OutboxEventPublisher(_make_session())
            await pub.publish("exchange", "routing_key", {})

        assert isinstance(calls[0]["aggregate_id"], uuid.UUID)

    @pytest.mark.asyncio
    async def test_delay_ms_is_ignored(self):
        """delay_ms parameter is accepted but discarded without error."""
        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        import infrastructure.publishers.outbox_event_publisher as pub_module

        with patch.object(pub_module.OutboxWriter, "write", new_callable=AsyncMock):
            pub = OutboxEventPublisher(_make_session())
            await pub.publish("exchange", "routing_key", {"user_id": str(uuid.uuid4())}, delay_ms=5000)


# ──────────────────────────────────────────────
# PatientProfileRepository
# ──────────────────────────────────────────────

def _mock_profile_model(user_id=None, profile_id=None):
    m = MagicMock()
    m.id = profile_id or uuid.uuid4()
    m.user_id = user_id or uuid.uuid4()
    m.full_name = "Test Patient"
    m.date_of_birth = date(1990, 1, 1)
    m.gender = "male"
    m.phone_number = "0901234567"
    m.address = "123 Street"
    m.avatar_url = None
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


def _mock_health_model(patient_id=None):
    m = MagicMock()
    m.patient_id = patient_id or uuid.uuid4()
    m.blood_type = "O+"
    m.height_cm = 170.0
    m.weight_kg = 65.0
    m.allergies = []
    m.chronic_conditions = []
    return m


def _mock_execute(scalar=None, scalars_list=None, rowcount=1):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalar_one.return_value = scalar
    mocks = MagicMock()
    mocks.all.return_value = scalars_list or ([scalar] if scalar else [])
    result.scalars.return_value = mocks
    result.rowcount = rowcount
    return result


class TestPatientProfileRepository:
    @pytest.mark.asyncio
    async def test_create_returns_entity(self):
        from infrastructure.repositories.repositories import PatientProfileRepository
        from Domain.entities.patient_profile import PatientProfile

        session = AsyncMock()
        model = _mock_profile_model()
        session.flush = AsyncMock()

        # session.add is sync
        session.add = MagicMock()

        repo = PatientProfileRepository(session)

        # The repository calls session.add(model) + session.flush(), then _to_entity(model)
        # We need to pass a PatientProfile entity
        profile = PatientProfile(
            id=model.id,
            user_id=model.user_id,
            full_name=model.full_name,
            date_of_birth=model.date_of_birth,
            gender=model.gender,
            phone_number=model.phone_number,
            address=model.address,
            avatar_url=model.avatar_url,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        result = await repo.create(profile)

        session.add.assert_called_once()
        session.flush.assert_called_once()
        assert result.full_name == "Test Patient"

    @pytest.mark.asyncio
    async def test_get_by_id_found(self):
        from infrastructure.repositories.repositories import PatientProfileRepository

        session = AsyncMock()
        model = _mock_profile_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=model))

        repo = PatientProfileRepository(session)
        result = await repo.get_by_id(model.id)

        assert result is not None
        assert result.full_name == "Test Patient"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        from infrastructure.repositories.repositories import PatientProfileRepository

        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=None))

        repo = PatientProfileRepository(session)
        result = await repo.get_by_id(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_user_id_found(self):
        from infrastructure.repositories.repositories import PatientProfileRepository

        session = AsyncMock()
        model = _mock_profile_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=model))

        repo = PatientProfileRepository(session)
        result = await repo.get_by_user_id(model.user_id)

        assert result is not None

    @pytest.mark.asyncio
    async def test_update_returns_entity(self):
        from infrastructure.repositories.repositories import PatientProfileRepository

        session = AsyncMock()
        model = _mock_profile_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=model))

        repo = PatientProfileRepository(session)
        result = await repo.update(model.id, full_name="Updated")

        assert result.full_name == "Test Patient"  # _to_entity(model) returns model's value

    @pytest.mark.asyncio
    async def test_delete_returns_true(self):
        from infrastructure.repositories.repositories import PatientProfileRepository

        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_execute(rowcount=1))

        repo = PatientProfileRepository(session)
        result = await repo.delete(uuid.uuid4())

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_not_found(self):
        from infrastructure.repositories.repositories import PatientProfileRepository

        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_execute(rowcount=0))

        repo = PatientProfileRepository(session)
        result = await repo.delete(uuid.uuid4())

        assert result is False


class TestPatientHealthRepository:
    @pytest.mark.asyncio
    async def test_create_returns_entity(self):
        from infrastructure.repositories.repositories import PatientHealthRepository
        from Domain.entities.patient_health_background import PatientHealthBackground

        session = AsyncMock()
        model = _mock_health_model()
        session.add = MagicMock()
        session.flush = AsyncMock()

        repo = PatientHealthRepository(session)

        background = PatientHealthBackground(
            patient_id=model.patient_id,
            blood_type=model.blood_type,
            height_cm=model.height_cm,
            weight_kg=model.weight_kg,
            allergies=model.allergies,
            chronic_conditions=model.chronic_conditions,
        )
        result = await repo.create(background)

        session.add.assert_called_once()
        session.flush.assert_called_once()
        assert result.blood_type == "O+"

    @pytest.mark.asyncio
    async def test_get_by_patient_id_found(self):
        from infrastructure.repositories.repositories import PatientHealthRepository

        session = AsyncMock()
        model = _mock_health_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=model))

        repo = PatientHealthRepository(session)
        result = await repo.get_by_patient_id(model.patient_id)

        assert result is not None
        assert result.blood_type == "O+"

    @pytest.mark.asyncio
    async def test_get_by_patient_id_not_found(self):
        from infrastructure.repositories.repositories import PatientHealthRepository

        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=None))

        repo = PatientHealthRepository(session)
        result = await repo.get_by_patient_id(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_update_returns_entity(self):
        from infrastructure.repositories.repositories import PatientHealthRepository

        session = AsyncMock()
        model = _mock_health_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=model))

        repo = PatientHealthRepository(session)
        result = await repo.update(model.patient_id, weight_kg=70.0)

        assert result.blood_type == "O+"
