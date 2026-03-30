import asyncio
import uuid
from datetime import datetime, time, timezone
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
# Shared helpers
# ──────────────────────────────────────────────

def _make_session():
    return AsyncMock()


def _mock_execute(scalar=None, scalars_list=None, rowcount=1):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalar_one.return_value = scalar
    mocks = MagicMock()
    mocks.all.return_value = scalars_list or ([scalar] if scalar else [])
    result.scalars.return_value = mocks
    result.rowcount = rowcount
    return result


def _mock_doctor_model(user_id=None, specialty_id=None):
    m = MagicMock()
    m.user_id = user_id or uuid.uuid4()
    m.specialty_id = specialty_id or uuid.uuid4()
    m.full_name = "Dr. Smith"
    m.title = "MD"
    m.experience_years = 10
    m.auto_confirm = False
    m.confirmation_timeout_minutes = 60
    return m


def _mock_schedule_model(schedule_id=None, doctor_id=None):
    m = MagicMock()
    m.id = schedule_id or uuid.uuid4()
    m.doctor_id = doctor_id or uuid.uuid4()
    m.day_of_week = "monday"
    m.start_time = time(9, 0)
    m.end_time = time(17, 0)
    m.slot_duration_minutes = 30
    return m


def _mock_specialty_model(specialty_id=None):
    m = MagicMock()
    m.id = specialty_id or uuid.uuid4()
    m.name = "Cardiology"
    m.description = "Heart specialist"
    return m


# ──────────────────────────────────────────────
# OutboxEventPublisher
# ──────────────────────────────────────────────

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

        async def fake_write(session, *, aggregate_id, **_kw):
            calls.append(aggregate_id)

        with patch.object(pub_module.OutboxWriter, "write", side_effect=fake_write):
            pub = OutboxEventPublisher(_make_session())
            await pub.publish("exchange", "routing_key", {"user_id": "not-a-uuid"})

        assert isinstance(calls[0], uuid.UUID)

    @pytest.mark.asyncio
    async def test_publish_without_ids_uses_random(self):
        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        import infrastructure.publishers.outbox_event_publisher as pub_module

        calls = []

        async def fake_write(session, *, aggregate_id, **_kw):
            calls.append(aggregate_id)

        with patch.object(pub_module.OutboxWriter, "write", side_effect=fake_write):
            pub = OutboxEventPublisher(_make_session())
            await pub.publish("exchange", "routing_key", {})

        assert isinstance(calls[0], uuid.UUID)

    @pytest.mark.asyncio
    async def test_delay_ms_is_ignored(self):
        from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher
        import infrastructure.publishers.outbox_event_publisher as pub_module

        with patch.object(pub_module.OutboxWriter, "write", new_callable=AsyncMock):
            pub = OutboxEventPublisher(_make_session())
            await pub.publish("exchange", "routing_key", {"user_id": str(uuid.uuid4())}, delay_ms=5000)


# ──────────────────────────────────────────────
# ScheduleRepository
# ──────────────────────────────────────────────

class TestScheduleRepository:
    @pytest.mark.asyncio
    async def test_save_merges_model(self):
        from infrastructure.repositories.schedule_repository import ScheduleRepository
        from Domain.entities.doctor_schedule import DoctorSchedule
        from Domain.value_objects.day_of_week import DayOfWeek

        session = AsyncMock()
        session.merge = AsyncMock()

        repo = ScheduleRepository(session)
        schedule = DoctorSchedule(
            id=uuid.uuid4(),
            doctor_id=uuid.uuid4(),
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(9, 0),
            end_time=time(17, 0),
            slot_duration_minutes=30,
        )
        result = await repo.save(schedule)

        session.merge.assert_called_once()
        assert result is schedule

    @pytest.mark.asyncio
    async def test_delete_executes_stmt(self):
        from infrastructure.repositories.schedule_repository import ScheduleRepository

        session = AsyncMock()
        session.execute = AsyncMock()

        repo = ScheduleRepository(session)
        await repo.delete(uuid.uuid4())

        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_doctor_and_day_returns_list(self):
        from infrastructure.repositories.schedule_repository import ScheduleRepository
        from Domain.value_objects.day_of_week import DayOfWeek

        session = AsyncMock()
        model = _mock_schedule_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalars_list=[model]))

        repo = ScheduleRepository(session)
        result = await repo.get_by_doctor_and_day(model.doctor_id, DayOfWeek.MONDAY)

        assert len(result) == 1
        assert result[0].slot_duration_minutes == 30

    @pytest.mark.asyncio
    async def test_list_by_doctor_returns_list(self):
        from infrastructure.repositories.schedule_repository import ScheduleRepository

        session = AsyncMock()
        model = _mock_schedule_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalars_list=[model]))

        repo = ScheduleRepository(session)
        result = await repo.list_by_doctor(model.doctor_id)

        assert len(result) == 1


# ──────────────────────────────────────────────
# SpecialtyRepository
# ──────────────────────────────────────────────

class TestSpecialtyRepository:
    @pytest.mark.asyncio
    async def test_save_merges_model(self):
        from infrastructure.repositories.specialty_repository import SpecialtyRepository
        from Domain.entities.specialty import Specialty

        session = AsyncMock()
        session.merge = AsyncMock()

        specialty = Specialty(id=uuid.uuid4(), name="Cardiology", description="Heart")
        repo = SpecialtyRepository(session)
        result = await repo.save(specialty)

        session.merge.assert_called_once()
        assert result is specialty

    @pytest.mark.asyncio
    async def test_get_by_id_found(self):
        from infrastructure.repositories.specialty_repository import SpecialtyRepository

        session = AsyncMock()
        model = _mock_specialty_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=model))

        repo = SpecialtyRepository(session)
        result = await repo.get_by_id(model.id)

        assert result is not None
        assert result.name == "Cardiology"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        from infrastructure.repositories.specialty_repository import SpecialtyRepository

        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=None))

        repo = SpecialtyRepository(session)
        result = await repo.get_by_id(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_name_found(self):
        from infrastructure.repositories.specialty_repository import SpecialtyRepository

        session = AsyncMock()
        model = _mock_specialty_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=model))

        repo = SpecialtyRepository(session)
        result = await repo.get_by_name("Cardiology")

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self):
        from infrastructure.repositories.specialty_repository import SpecialtyRepository

        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=None))

        repo = SpecialtyRepository(session)
        result = await repo.get_by_name("NonExistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_all_returns_list(self):
        from infrastructure.repositories.specialty_repository import SpecialtyRepository

        session = AsyncMock()
        model = _mock_specialty_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalars_list=[model]))

        repo = SpecialtyRepository(session)
        result = await repo.list_all()

        assert len(result) == 1
        assert result[0].name == "Cardiology"


# ──────────────────────────────────────────────
# DoctorRepository
# ──────────────────────────────────────────────

class TestDoctorRepository:
    @pytest.mark.asyncio
    async def test_get_by_id_found(self):
        from infrastructure.repositories.doctor_repository import DoctorRepository

        session = AsyncMock()
        model = _mock_doctor_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=model))

        repo = DoctorRepository(session)
        result = await repo.get_by_id(model.user_id)

        assert result is not None
        assert result.full_name == "Dr. Smith"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        from infrastructure.repositories.doctor_repository import DoctorRepository

        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_execute(scalar=None))

        repo = DoctorRepository(session)
        result = await repo.get_by_id(uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_specialty_returns_list(self):
        from infrastructure.repositories.doctor_repository import DoctorRepository

        session = AsyncMock()
        model = _mock_doctor_model()
        session.execute = AsyncMock(return_value=_mock_execute(scalars_list=[model]))

        repo = DoctorRepository(session)
        result = await repo.list_by_specialty(model.specialty_id)

        assert len(result) == 1
        assert result[0].full_name == "Dr. Smith"
