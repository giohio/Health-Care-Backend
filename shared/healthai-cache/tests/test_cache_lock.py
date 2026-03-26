import pytest
from unittest.mock import AsyncMock, MagicMock
from healthai_cache.lock import DistributedLock

@pytest.fixture
def mock_redis():
    redis = MagicMock() # Use MagicMock for the client
    redis.set = AsyncMock(return_value=True)
    redis.eval = AsyncMock(return_value=1)
    # register_script is SYNC, but returns an object that is CALLED (async)
    script_mock = AsyncMock(return_value=1)
    redis.register_script.return_value = script_mock
    return redis

@pytest.mark.asyncio
async def test_lock_acquire_release(mock_redis):
    lock = DistributedLock(mock_redis)
    
    # 1. Acquire
    token = await lock.acquire("my-resource", ttl=10)
    assert token is not None
    mock_redis.set.assert_called()
    
    # 2. Release (calls the mocked lua script)
    success = await lock.release("my-resource", token)
    assert success is True
    mock_redis.register_script.return_value.assert_called()

@pytest.mark.asyncio
async def test_lock_extend(mock_redis):
    lock = DistributedLock(mock_redis)
    success = await lock.extend("my-resource", "token123", additional_ttl=30)
    assert success is True
    mock_redis.eval.assert_called()

@pytest.mark.asyncio
async def test_lock_context_manager(mock_redis):
    lock = DistributedLock(mock_redis)
    
    async with lock.context("auto-resource") as acquired:
        assert acquired is True
        mock_redis.set.assert_called()
    
    # Verify auto-release
    mock_redis.register_script.return_value.assert_called()
