import pytest
from unittest.mock import AsyncMock, MagicMock
from healthai_events.relay import OutboxRelay
from healthai_db import OutboxEvent
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture
def mock_session_factory():
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.begin.return_value.__aenter__ = AsyncMock()
    session.begin.return_value.__aexit__ = AsyncMock()
    
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock()
    return factory

@pytest.mark.asyncio
async def test_relay_no_events(mock_session_factory):
    relay = OutboxRelay(mock_session_factory, AsyncMock())
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session = mock_session_factory.return_value.__aenter__.return_value
    session.execute = AsyncMock(return_value=mock_result)
    
    count = await relay._process_batch()
    assert count == 0

@pytest.mark.asyncio
async def test_relay_with_non_retryable_error(mock_session_factory):
    publisher = AsyncMock()
    from healthai_events.exceptions import NonRetryableError
    publisher.publish.side_effect = NonRetryableError("Fatal")
    
    relay = OutboxRelay(mock_session_factory, publisher)
    event = OutboxEvent(id=1, status="pending", retry_count=0)
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [event]
    session = mock_session_factory.return_value.__aenter__.return_value
    session.execute = AsyncMock(return_value=mock_result)
    
    await relay._process_batch()
    
    assert event.status == "failed"
    assert "Fatal" in event.last_error
