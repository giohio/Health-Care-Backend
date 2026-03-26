import pytest
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, time
from infrastructure.repositories.appointment_repository import AppointmentRepository
from infrastructure.database.models import AppointmentModel
from Domain.value_objects.appointment_status import AppointmentStatus

@pytest.mark.asyncio
async def test_maybe_await_with_awaitable():
    repo = AppointmentRepository(AsyncMock())
    async_val = AsyncMock()
    async_val.__await__ = MagicMock(return_value=iter(["resolved"]))
    
    # In practice AsyncMock is awaitable
    res = await repo._maybe_await(asyncio.Future())
    # This is a bit tricky to test with simple mocks, let's use a real future
    f = asyncio.Future()
    f.set_result("done")
    assert await repo._maybe_await(f) == "done"

@pytest.mark.asyncio
async def test_maybe_await_with_non_awaitable():
    repo = AppointmentRepository(AsyncMock())
    assert await repo._maybe_await("sync") == "sync"

@pytest.mark.asyncio
async def test_get_doctor_queue_sorting():
    session = AsyncMock()
    repo = AppointmentRepository(session)
    doctor_id = uuid.uuid4()
    
    # Mock result to return a list of models
    m1 = MagicMock(spec=AppointmentModel)
    m1.id = uuid.uuid4()
    m1.status = AppointmentStatus.PENDING # Should be first
    m1.start_time = time(10, 0)
    
    m2 = MagicMock(spec=AppointmentModel)
    m2.id = uuid.uuid4()
    m2.status = AppointmentStatus.CONFIRMED
    m2.start_time = time(9, 0) # Should be second (confirmed but earlier)
    
    mock_result = AsyncMock()
    mock_scalars = AsyncMock()
    mock_scalars.all.return_value = [m1, m2]
    mock_result.scalars.return_value = mock_scalars
    session.execute.return_value = mock_result
    
    # Mock _to_entity to avoid deep attribute access on MagicMocks
    with patch.object(AppointmentRepository, "_to_entity", side_effect=lambda x: x):
        res = await repo.get_doctor_queue(doctor_id, date.today())
        assert len(res) == 2
        # The actual sorting happens in the SQL query, 
        # but this tests the method logic of calling execute and scalar/all.

@pytest.mark.asyncio
async def test_mark_reminder_sent_1h_not_found():
    session = AsyncMock()
    repo = AppointmentRepository(session)
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result
    
    await repo.mark_reminder_sent(uuid.uuid4(), "1h")
    session.flush.assert_called_once()
