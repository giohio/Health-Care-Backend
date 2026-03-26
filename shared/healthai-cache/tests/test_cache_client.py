import pytest
from unittest.mock import AsyncMock, MagicMock
from healthai_cache.client import CacheClient

@pytest.fixture
def mock_redis():
    return AsyncMock()

@pytest.mark.asyncio
async def test_cache_client_basic_ops(mock_redis):
    client = CacheClient(mock_redis)
    
    # Test set/get (set calls setex)
    await client.set("key", "val", ttl=60)
    mock_redis.setex.assert_called()
    
    mock_redis.get.return_value = b'"val"'
    assert await client.get("key") == "val"
    
    # Test delete
    await client.delete("key")
    mock_redis.delete.assert_called_with("key")
