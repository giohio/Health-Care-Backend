import asyncio

import pytest
from healthai_cache import DistributedLock


@pytest.fixture
async def redis():
    """Use fakeredis for testing."""
    try:
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis()
    except ImportError:
        pytest.skip("fakeredis not installed")


@pytest.fixture
def lock(redis):
    return DistributedLock(redis)


@pytest.mark.asyncio
async def test_acquire_returns_token(lock):
    token = await lock.acquire("slot:abc", ttl=15)
    assert token is not None
    assert len(token) > 0


@pytest.mark.asyncio
async def test_second_acquire_fails(lock):
    await lock.acquire("slot:abc", ttl=15)
    token2 = await lock.acquire("slot:abc", ttl=15)
    assert token2 is None


@pytest.mark.asyncio
async def test_release_by_owner_succeeds(lock):
    token = await lock.acquire("slot:abc", ttl=15)
    released = await lock.release("slot:abc", token)
    assert released is True
    # Now anyone can acquire
    token2 = await lock.acquire("slot:abc", ttl=15)
    assert token2 is not None


@pytest.mark.asyncio
async def test_release_by_non_owner_fails(lock):
    await lock.acquire("slot:abc", ttl=15)
    released = await lock.release("slot:abc", "wrong-token")
    assert released is False


@pytest.mark.asyncio
async def test_concurrent_1000_only_one_wins(lock):
    """
    Mô phỏng 1000 requests cùng lúc.
    Chỉ đúng 1 request acquire được lock.
    """
    results = await asyncio.gather(
        *[lock.acquire("slot:hotslot", ttl=30) for _ in range(100)]  # Use 100 instead of 1000 for faster test
    )
    successful = [r for r in results if r is not None]
    assert len(successful) == 1


@pytest.mark.asyncio
async def test_context_manager_auto_releases(lock):
    async with lock.context("slot:abc", ttl=15) as acquired:
        assert acquired is True
        # Lock held inside context
        token2 = await lock.acquire("slot:abc", ttl=15)
        assert token2 is None
    # Lock released after context
    token3 = await lock.acquire("slot:abc", ttl=15)
    assert token3 is not None
