import pytest
from healthai_db import Base, OutboxEvent, OutboxWriter, create_session_factory
from sqlalchemy import select
from uuid_extension import uuid7


@pytest.fixture
async def session_factory():
    """Create test session factory."""
    # For testing, use sqlite in-memory
    factory = create_session_factory("sqlite+aiosqlite:///:memory:", echo=False)
    async with factory() as session:
        async with session.begin():
            # Create tables
            await session.run_sync(Base.metadata.create_all)
    return factory


@pytest.mark.asyncio
async def test_outbox_write_single(session_factory):
    """Test writing single outbox event."""
    async with session_factory() as session:
        appt_id = uuid7()
        await OutboxWriter.write(
            session,
            aggregate_id=appt_id,
            aggregate_type="appointment_events",
            event_type="appointment.created",
            payload={"appointment_id": str(appt_id)},
        )
        await session.commit()

        # Verify event was persisted
        result = await session.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == appt_id))
        persisted = result.scalar_one()
        assert persisted.status == "pending"
        assert persisted.event_type == "appointment.created"
        assert persisted.payload["appointment_id"] == str(appt_id)


@pytest.mark.asyncio
async def test_outbox_write_many(session_factory):
    """Test bulk write multiple events."""
    async with session_factory() as session:
        events_data = [
            {
                "aggregate_id": uuid7(),
                "aggregate_type": "user_events",
                "event_type": "user.registered",
                "payload": {"user_id": str(uuid7())},
            }
            for _ in range(3)
        ]

        await OutboxWriter.write_many(session, events_data)
        await session.commit()

        result = await session.execute(select(OutboxEvent).where(OutboxEvent.aggregate_type == "user_events"))
        persisted = result.scalars().all()
        assert len(persisted) == 3


@pytest.mark.asyncio
async def test_outbox_atomicity(session_factory):
    """Test atomicity — if commit fails, outbox not inserted."""
    async with session_factory() as session:
        appt_id = uuid7()
        await OutboxWriter.write(
            session, aggregate_id=appt_id, aggregate_type="test", event_type="test.event", payload={}
        )
        # No commit — should roll back

    # Verify not persisted
    async with session_factory() as session:
        result = await session.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == appt_id))
        persisted = result.scalar_one_or_none()
        assert persisted is None
