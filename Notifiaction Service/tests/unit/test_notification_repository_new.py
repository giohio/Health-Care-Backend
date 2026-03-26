import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from infrastructure.repositories.notification_repository import NotificationRepository
from infrastructure.database.models import NotificationModel
from Domain.entities.notification import Notification

@pytest.mark.asyncio
async def test_notification_repository_save():
    session = AsyncMock()
    repo = NotificationRepository(session)
    notif = Notification(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="Test",
        body="Body",
        event_type="test_event"
    )
    
    await repo.save(notif)
    session.merge.assert_called_once()

@pytest.mark.asyncio
async def test_notification_repository_get_by_id_success():
    session = AsyncMock()
    repo = NotificationRepository(session)
    notif_id = uuid.uuid4()
    
    mock_model = MagicMock(spec=NotificationModel)
    mock_model.id = notif_id
    mock_model.user_id = uuid.uuid4()
    mock_model.title = "Test"
    mock_model.body = "Body"
    mock_model.is_read = False
    mock_model.created_at = datetime.now(timezone.utc)
    mock_model.read_at = None
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    session.execute.return_value = mock_result
    
    res = await repo.get_by_id(notif_id)
    assert res.id == notif_id
    assert res.title == "Test"

@pytest.mark.asyncio
async def test_notification_repository_mark_read_success():
    session = AsyncMock()
    repo = NotificationRepository(session)
    notif_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    mock_model = MagicMock(spec=NotificationModel)
    mock_model.id = notif_id
    mock_model.user_id = user_id
    mock_model.title = "Test"
    mock_model.body = "Body"
    mock_model.is_read = False
    mock_model.event_type = "test"
    mock_model.created_at = datetime.now(timezone.utc)
    mock_model.read_at = None
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_model
    session.execute.return_value = mock_result
    
    res = await repo.mark_read(notif_id)
    assert res.is_read is True
    session.commit.assert_called_once()

@pytest.mark.asyncio
async def test_notification_repository_count_unread():
    session = AsyncMock()
    repo = NotificationRepository(session)
    
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 5
    session.execute.return_value = mock_result
    
    count = await repo.count_unread(uuid.uuid4())
    assert count == 5

@pytest.mark.asyncio
async def test_notification_repository_mark_all_read():
    session = AsyncMock()
    repo = NotificationRepository(session)
    
    mock_result = MagicMock()
    mock_result.rowcount = 10
    session.execute.return_value = mock_result
    
    updated = await repo.mark_all_read(uuid.uuid4())
    assert updated == 10
    session.commit.assert_called_once()
