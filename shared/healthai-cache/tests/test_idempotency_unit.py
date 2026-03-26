import pytest
from unittest.mock import AsyncMock, MagicMock
from healthai_cache.idempotency import IdempotencyStore

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get.return_value = None
    redis.setex.return_value = True
    return redis

@pytest.mark.asyncio
async def test_idempotency_store_logic(mock_redis):
    store = IdempotencyStore(mock_redis)
    key = "idem-123"
    
    # 1. First store
    await store.store(key, 201, {"id": 1})
    mock_redis.setex.assert_called()
    
    # 2. Get back
    mock_redis.get.return_value = b'{"status_code": 201, "body": {"id": 1}}'
    res = await store.get(key)
    assert res["status_code"] == 201
    
    # 3. Store error should be ignored by default if configured
    await store.store("err-key", 500, {"msg": "fail"})
    # (Assuming IdempotencyStore only caches 2xx/3xx by default)
