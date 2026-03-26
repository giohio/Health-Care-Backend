import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from fastapi import Request, Response
from healthai_common.idempotency import idempotent

@pytest.mark.asyncio
async def test_idempotent_decorator_replay():
    # Mocking FastAPI Request and Cache
    mock_cache = MagicMock()
    # mock_cache.idempotency.get returns a dict
    mock_cache.idempotency.get = AsyncMock(return_value={
        "status_code": 200,
        "body": {"status": "replayed"}
    })
    
    request = MagicMock(spec=Request)
    request.method = "POST"
    request.headers = {"Idempotency-Key": "unique-123"}
    request.app.state.cache = mock_cache
    
    # The decorated function
    @idempotent(ttl=10)
    async def my_handler(req, cache=None):
        return {"status": "fresh"}

    response = await my_handler(request)
    
    # Verify it returned JSONResponse with cached body
    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "replayed"}
    assert response.headers["X-Idempotent-Replayed"] == "true"

@pytest.mark.asyncio
async def test_idempotent_decorator_fresh_execution():
    mock_cache = MagicMock()
    mock_cache.idempotency.get = AsyncMock(return_value=None)
    mock_cache.idempotency.store = AsyncMock()
    
    request = MagicMock(spec=Request)
    request.method = "POST"
    request.headers = {"Idempotency-Key": "new-key"}
    request.app.state.cache = mock_cache
    
    # Mock response object that has status_code and body
    fresh_response = MagicMock(spec=Response)
    fresh_response.status_code = 201
    fresh_response.body = b'{"status": "created"}'
    
    @idempotent(ttl=1)
    async def my_handler(req, cache=None):
        return fresh_response

    result = await my_handler(request)
    
    assert result == fresh_response
    mock_cache.idempotency.store.assert_awaited_once_with(
        "new-key", 201, {"status": "created"}, ttl=1
    )
