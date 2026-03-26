import pytest
from unittest.mock import AsyncMock, MagicMock
from healthai_events.consumer import BaseConsumer

# Define FakeConsumer instead of TestConsumer to avoid pytest collection issues
class FakeConsumer(BaseConsumer):
    QUEUE = "test.queue"
    EXCHANGE = "test.exchange"
    ROUTING_KEY = "test.event"
    
    async def handle(self, payload: dict):
        # Implementation intentionally empty for base consumer unit testing
        pass

@pytest.fixture
def mock_connection():
    conn = AsyncMock()
    channel = AsyncMock()
    conn.channel.return_value = channel
    return conn

@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get.return_value = None
    return cache

@pytest.mark.asyncio
async def test_base_consumer_process_success(mock_connection, mock_cache):
    consumer = FakeConsumer(mock_connection, mock_cache)
    consumer.handle = AsyncMock()
    
    # Mock pika message
    message = MagicMock()
    message.message_id = "msg-123"
    message.body = b'{"foo": "bar"}'
    message.headers = {}
    
    # process() is a sync call returning an object with async context manager methods
    message.process.return_value.__aenter__ = AsyncMock()
    message.process.return_value.__aexit__ = AsyncMock()

    await consumer._process(message)
    
    consumer.handle.assert_awaited_with({"foo": "bar"})
    mock_cache.set.assert_called()
