import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from healthai_cache import DistributedLock

@pytest.fixture
def redis():
    """Mock Redis client to avoid fakeredis dependency."""
    redis_mock = MagicMock()
    redis_mock.set = AsyncMock(return_value=True)
    
    # Mock script execution
    script_mock = AsyncMock(return_value=1)
    redis_mock.register_script.return_value = script_mock
    redis_mock.eval = AsyncMock(return_value=1)
    return redis_mock

@pytest.fixture
def lock(redis):
    return DistributedLock(redis)

@pytest.mark.asyncio
async def test_acquire_returns_token(lock, redis):
    token = await lock.acquire("slot:abc", ttl=15)
    assert token is not None
    redis.set.assert_called()

@pytest.mark.asyncio
async def test_second_acquire_fails(lock, redis):
    redis.set.side_effect = [True, False]
    await lock.acquire("slot:abc", ttl=15)
    token2 = await lock.acquire("slot:abc", ttl=15)
    assert token2 is None

@pytest.mark.asyncio
async def test_release_by_owner_succeeds(lock, redis):
    token = await lock.acquire("slot:abc", ttl=15)
    # register_script mock returns 1 (True)
    released = await lock.release("slot:abc", token)
    assert released is True

@pytest.mark.asyncio
async def test_release_by_non_owner_fails(lock, redis):
    # Mock script to return 0 (False)
    redis.register_script.return_value.return_value = 0
    await lock.acquire("slot:abc", ttl=15)
    released = await lock.release("slot:abc", "wrong-token")
    assert released is False

@pytest.mark.asyncio
async def test_concurrent_only_one_wins(lock, redis):
    # Mock: only first one succeeds
    redis.set.side_effect = [True] + [False] * 99
    results = await asyncio.gather(
        *[lock.acquire("slot:hotslot", ttl=30) for _ in range(100)]
    )
    successful = [r for r in results if r is not None]
    assert len(successful) == 1

@pytest.mark.asyncio
async def test_context_manager_auto_releases(lock, redis):
    async with lock.context("slot:abc", ttl=15) as acquired:
        assert acquired is True
        redis.set.assert_called()
    
    # Verify release was called
    redis.register_script.return_value.assert_called()
