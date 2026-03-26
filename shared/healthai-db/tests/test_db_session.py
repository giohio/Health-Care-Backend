import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, AsyncEngine
from healthai_db.session import create_session_factory, get_session
import os

@pytest.mark.asyncio
async def test_create_session_factory():
    """Test that create_session_factory works without real aiosqlite."""
    with patch("healthai_db.session.create_async_engine") as mock_create:
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_create.return_value = mock_engine
        
        database_url = "postgresql+asyncpg://ci:ci@localhost/db"
        factory = create_session_factory(database_url)
        
        assert isinstance(factory, async_sessionmaker)
        assert factory.kw["bind"] == mock_engine

@pytest.mark.asyncio
async def test_get_session_rollback_on_error():
    """Test that get_session rolls back on exception."""
    mock_session = AsyncMock(spec=AsyncSession)
    
    # Mock behavior of session_factory() returning an async context manager
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    
    mock_factory = MagicMock(return_value=mock_cm)
    
    with pytest.raises(ValueError, match="Test Error"):
        async with get_session(mock_factory) as session:
            assert session == mock_session
            raise ValueError("Test Error")
    
    mock_session.rollback.assert_awaited_once()
