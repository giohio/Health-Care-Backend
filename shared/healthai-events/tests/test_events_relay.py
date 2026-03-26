import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from healthai_events.relay import OutboxRelay
from healthai_db import OutboxEvent

@pytest.fixture
def mock_session_factory():
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.add = MagicMock()
    
    # Mock session.begin() as an async context manager
    session.begin.return_value.__aenter__ = AsyncMock()
    session.begin.return_value.__aexit__ = AsyncMock()
    
    # Mock session_factory() as an async context manager
    factory_mock = MagicMock()
    factory_mock.return_value.__aenter__ = AsyncMock(return_value=session)
    factory_mock.return_value.__aexit__ = AsyncMock()
    return factory_mock

@pytest.fixture
def mock_publisher():
    return AsyncMock()

@pytest.mark.asyncio
async def test_relay_process_batch_success(mock_session_factory, mock_publisher):
    relay = OutboxRelay(mock_session_factory, mock_publisher)
    
    # Mock events returned by DB
    event = OutboxEvent(
        id=1, 
        aggregate_type="test_agg", 
        event_type="test_event", 
        payload={"foo": "bar"},
        status="pending",
        retry_count=0
    )
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [event]
    
    session = mock_session_factory.return_value.__aenter__.return_value
    session.execute = AsyncMock(return_value=mock_result)
    
    processed_count = await relay._process_batch()
    
    assert processed_count == 1
    mock_publisher.publish.assert_awaited_once()
    assert event.status == "published"
    assert event.published_at is not None

@pytest.mark.asyncio
async def test_relay_process_batch_retry_on_failure(mock_session_factory, mock_publisher):
    relay = OutboxRelay(mock_session_factory, mock_publisher)
    mock_publisher.publish.side_effect = Exception("Network error")
    
    event = OutboxEvent(id=1, status="pending", retry_count=0)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [event]
    
    session = mock_session_factory.return_value.__aenter__.return_value
    session.execute = AsyncMock(return_value=mock_result)
    
    await relay._process_batch()
    
    assert event.retry_count == 1
    assert event.status == "pending" # remains pending for retry
    assert "Network error" in event.last_error

@pytest.mark.asyncio
async def test_relay_permanent_failure(mock_session_factory, mock_publisher):
    relay = OutboxRelay(mock_session_factory, mock_publisher)
    relay.MAX_RETRIES = 1
    mock_publisher.publish.side_effect = Exception("Fatal error")
    
    event = OutboxEvent(id=1, status="pending", retry_count=1)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [event]
    
    session = mock_session_factory.return_value.__aenter__.return_value
    session.execute = AsyncMock(return_value=mock_result)
    
    await relay._process_batch()
    
    assert event.status == "failed"
