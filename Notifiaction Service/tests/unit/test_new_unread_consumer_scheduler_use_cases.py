from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import asyncio

import pytest
from Application.use_cases.get_unread_count import GetUnreadCountUseCase
from Application.use_cases.mark_all_read import MarkAllReadUseCase
from infrastructure.consumers.appointment_events_consumers import AppointmentStartedConsumer


class _FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        await asyncio.sleep(0)
        self.commits += 1


class _SessionFactory:
    def __init__(self):
        self.session = _FakeSession()

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeCache:
    def __init__(self, values=None):
        self.values = values or {}
        self.setex_calls = []
        self.delete_calls = []

    async def get(self, key):
        await asyncio.sleep(0)
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        await asyncio.sleep(0)
        self.setex_calls.append((key, ttl, value))

    async def delete(self, key):
        await asyncio.sleep(0)
        self.delete_calls.append(key)


@pytest.mark.asyncio
async def test_unread_count_and_mark_all_read_delegate_to_repo():
    repo = SimpleNamespace(count_unread=AsyncMock(return_value=3), mark_all_read=AsyncMock(return_value=5))

    unread = await GetUnreadCountUseCase(repo).execute("user-1")
    changed = await MarkAllReadUseCase(repo).execute("user-1")

    assert unread == 3
    assert changed == 5
    repo.count_unread.assert_awaited_once_with("user-1")
    repo.mark_all_read.assert_awaited_once_with("user-1")


@pytest.mark.asyncio
async def test_appointment_started_consumer_creates_notification_via_use_case_factory():
    sink = []

    class FakeUC:
        async def execute(self, **kwargs):
            await asyncio.sleep(0)
            sink.append(kwargs)

    session_factory = _SessionFactory()
    consumer = AppointmentStartedConsumer(
        connection=object(),
        cache=object(),
        session_factory=session_factory,
        create_notification_use_case_factory=lambda _session: FakeUC(),
    )

    await consumer.handle({"patient_id": "p-1", "patient_email": "p@example.com"})

    assert len(sink) == 1
    assert sink[0]["user_id"] == "p-1"
    assert sink[0]["event_type"] == "appointment.started"
    assert sink[0]["recipient_email"] == "p@example.com"
    assert session_factory.session.commits == 1


@pytest.mark.asyncio
async def test_unread_count_use_case_returns_cached_value_without_repo_call():
    repo = SimpleNamespace(count_unread=AsyncMock())
    cache = FakeCache(values={"notif:unread:user-1": "7"})

    result = await GetUnreadCountUseCase(repo, cache=cache).execute("user-1")

    assert result == 7
    repo.count_unread.assert_not_awaited()


@pytest.mark.asyncio
async def test_unread_count_use_case_returns_decoded_cached_integer_without_repo_call():
    repo = SimpleNamespace(count_unread=AsyncMock())
    cache = FakeCache(values={"notif:unread:user-1": 9})

    result = await GetUnreadCountUseCase(repo, cache=cache).execute("user-1")

    assert result == 9
    repo.count_unread.assert_not_awaited()


@pytest.mark.asyncio
async def test_unread_count_use_case_sets_cache_with_ttl_on_miss():
    repo = SimpleNamespace(count_unread=AsyncMock(return_value=4))
    cache = FakeCache()

    result = await GetUnreadCountUseCase(repo, cache=cache).execute("user-2")

    assert result == 4
    assert cache.setex_calls == [("notif:unread:user-2", 60, 4)]


@pytest.mark.asyncio
async def test_mark_all_read_use_case_invalidates_unread_count_cache():
    repo = SimpleNamespace(mark_all_read=AsyncMock(return_value=2))
    cache = FakeCache()

    changed = await MarkAllReadUseCase(repo, cache=cache).execute("user-3")

    assert changed == 2
    assert cache.delete_calls == ["notif:unread:user-3"]

