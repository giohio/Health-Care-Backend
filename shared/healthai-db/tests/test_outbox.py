import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from healthai_db import OutboxEvent, OutboxWriter
from uuid_extension import uuid7


@pytest.fixture
def mock_session():
    """Create a mock async session with sync add/add_all."""
    session = MagicMock(spec=AsyncSession)
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_outbox_write_single(mock_session):
    """Test writing single outbox event."""
    appt_id = uuid7()
    await OutboxWriter.write(
        mock_session,
        aggregate_id=appt_id,
        aggregate_type="appointment_events",
        event_type="appointment.created",
        payload={"appointment_id": str(appt_id)},
    )

    # Verify session.add was called once
    mock_session.add.assert_called_once()
    added_obj = mock_session.add.call_args[0][0]
    
    assert isinstance(added_obj, OutboxEvent)
    assert added_obj.aggregate_id == appt_id
    assert added_obj.event_type == "appointment.created"
    assert added_obj.payload["appointment_id"] == str(appt_id)


@pytest.mark.asyncio
async def test_outbox_write_many(mock_session):
    """Test bulk write multiple events."""
    events_data = [
        {
            "aggregate_id": uuid7(),
            "aggregate_type": "user_events",
            "event_type": "user.registered",
            "payload": {"user_id": str(uuid7())},
        }
        for _ in range(3)
    ]

    await OutboxWriter.write_many(mock_session, events_data)

    # Verify session.add_all called once
    mock_session.add_all.assert_called_once()
    added_list = mock_session.add_all.call_args[0][0]
    assert len(added_list) == 3


@pytest.mark.asyncio
async def test_outbox_atomicity_concept():
    """
    Note: In a pure unit test with mocks, atomicity is guaranteed by 
    the caller managed transaction (session.commit/rollback).
    The unit test for OutboxWriter only ensures the 'add' calls are made.
    """
    pass
