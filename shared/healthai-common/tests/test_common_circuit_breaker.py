import pytest
from unittest.mock import AsyncMock, MagicMock
from healthai_common.circuit_breaker import CircuitBreaker, CircuitOpenError

@pytest.fixture
def mock_cache():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.delete = AsyncMock()
    # Mock lower level redis client access
    cache._redis = AsyncMock()
    return cache

@pytest.mark.asyncio
async def test_circuit_breaker_closed_to_open(mock_cache):
    cb = CircuitBreaker("test-svc", mock_cache, failure_threshold=2)
    
    # Mock a failing function
    fail_fn = AsyncMock(side_effect=ValueError("API Down"))
    
    # 1. First failure
    mock_cache._redis.incr.return_value = 1
    with pytest.raises(ValueError):
        await cb.call(fail_fn)
    
    # 2. Second failure -> Open
    mock_cache._redis.incr.return_value = 2
    with pytest.raises(ValueError):
        await cb.call(fail_fn)
    
    # Verify it tried to set state to OPEN
    mock_cache.set.assert_called_with("cb:test-svc:state", "OPEN", ttl=30)

@pytest.mark.asyncio
async def test_circuit_breaker_open_blocks_call(mock_cache):
    mock_cache.get.return_value = "OPEN"
    cb = CircuitBreaker("test-svc", mock_cache)
    
    fn = AsyncMock()
    with pytest.raises(CircuitOpenError):
        await cb.call(fn)
    
    fn.assert_not_called()

@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery(mock_cache):
    mock_cache.get.return_value = "HALF_OPEN"
    # mock_cache._redis.set(..., nx=True) returns True for the first probe
    mock_cache._redis.set.return_value = True 
    cb = CircuitBreaker("test-svc", mock_cache)
    
    fn = AsyncMock(return_value="ok")
    result = await cb.call(fn)
    
    assert result == "ok"
    # Success in HALF_OPEN resets to CLOSED
    mock_cache.delete.assert_called()
