import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from datetime import datetime, timezone

from presentation.routes.auth import get_me

@pytest.mark.asyncio
async def test_get_me_success():
    mock_repo = AsyncMock()
    user_id = uuid4()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.email = "test@example.com"
    mock_user.role = "patient"
    mock_user.is_active = True
    dt = datetime.now(timezone.utc)
    mock_user.created_at = dt
    mock_repo.get_by_id.return_value = mock_user

    response = await get_me(x_user_id=str(user_id), user_repo=mock_repo)
    assert response.id == user_id
    assert response.email == "test@example.com"
    assert response.role == "patient"
    assert response.is_active is True
    assert response.created_at == dt.isoformat()
    mock_repo.get_by_id.assert_called_once_with(user_id)

@pytest.mark.asyncio
async def test_get_me_missing_header():
    with pytest.raises(HTTPException) as exc_info:
        await get_me(x_user_id=None, user_repo=AsyncMock())
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unauthenticated"

@pytest.mark.asyncio
async def test_get_me_invalid_uuid():
    with pytest.raises(HTTPException) as exc_info:
        await get_me(x_user_id="invalid-uuid", user_repo=AsyncMock())
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid user ID"

@pytest.mark.asyncio
async def test_get_me_user_not_found():
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        await get_me(x_user_id=str(uuid4()), user_repo=mock_repo)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "User not found"
