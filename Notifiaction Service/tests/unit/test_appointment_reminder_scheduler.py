import sys
from unittest.mock import MagicMock
# Mock apscheduler modules before they are imported by the code under test
mock_apscheduler = MagicMock()
sys.modules["apscheduler"] = mock_apscheduler
sys.modules["apscheduler.schedulers"] = MagicMock()
sys.modules["apscheduler.schedulers.asyncio"] = MagicMock()
sys.modules["apscheduler.triggers"] = MagicMock()
sys.modules["apscheduler.triggers.interval"] = MagicMock()

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from infrastructure.scheduler.appointment_reminder_scheduler import AppointmentReminderScheduler

class _FakeSession:
    async def commit(self):
        pass
    async def flush(self):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass

class _SessionFactory:
    def __init__(self, session):
        self.session = session
    def __call__(self):
        return self
    async def __aenter__(self):
        return self.session
    async def __aexit__(self, exc_type, exc, tb):
        pass

@pytest.mark.asyncio
async def test_check_reminders_sends_24h_and_1h():
    now = datetime(2026, 1, 1, 10, 0, 0)
    
    appt_24h = {
        "id": "a-24h",
        "appointment_date": "2026-01-02",
        "start_time": "10:00:00",
        "patient_id": "p-1",
        "reminder_24h_sent": False
    }
    appt_1h = {
        "id": "a-1h",
        "appointment_date": "2026-01-01",
        "start_time": "11:00:00",
        "patient_id": "p-2",
        "reminder_1h_sent": False
    }

    mock_client = AsyncMock()
    mock_client.get_upcoming_appointments.return_value = [appt_24h, appt_1h]
    
    mock_cache = AsyncMock()
    mock_cache.exists.return_value = False
    
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    session_factory = _SessionFactory(mock_session)
    
    scheduler = AppointmentReminderScheduler(session_factory, mock_client, mock_cache)

    # Patch both the datetime in the module and the NotificationRepository
    with patch("infrastructure.scheduler.appointment_reminder_scheduler.datetime") as mock_dt, \
         patch("infrastructure.repositories.notification_repository.NotificationRepository") as mock_repo_class:
        
        mock_dt.now.return_value = now
        # Re-attach real methods to the mock if they are used as class methods
        mock_dt.fromisoformat = datetime.fromisoformat
        mock_dt.combine = datetime.combine
        
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock()
        mock_repo_class.return_value = mock_repo

        await scheduler._check_reminders()

    # Verify both were sent
    # print(f"Calls: {mock_client.mark_reminder_sent.call_args_list}")
    assert mock_client.mark_reminder_sent.call_count == 2
    mock_client.mark_reminder_sent.assert_any_call("a-24h", "24h")
    mock_client.mark_reminder_sent.assert_any_call("a-1h", "1h")

@pytest.mark.asyncio
async def test_send_reminder_already_locked_skips():
    mock_client = AsyncMock()
    mock_cache = AsyncMock()
    mock_cache.exists.return_value = True # Already exists
    
    scheduler = AppointmentReminderScheduler(None, mock_client, mock_cache)
    await scheduler._send_reminder({"id": "some-id", "patient_id": "p-1"}, "1h")
    
    mock_client.mark_reminder_sent.assert_not_awaited()

@pytest.mark.asyncio
async def test_start_stop():
    scheduler = AppointmentReminderScheduler(None, None, None)
    # Mock the internal scheduler instance created in __init__
    scheduler.scheduler = MagicMock()
    
    # Simulate start
    scheduler.scheduler.running = True
    await scheduler.start()
    assert scheduler.scheduler.running
    
    # Simulate stop
    scheduler.scheduler.running = False
    await scheduler.stop()
    assert not scheduler.scheduler.running
