import asyncio
from uuid import uuid4

import pytest
from infrastructure.database import session as session_module
from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher


@pytest.mark.asyncio
async def test_get_db_commit_and_rollback(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        async def commit(self):
            await asyncio.sleep(0)
            self.commits += 1

        async def rollback(self):
            await asyncio.sleep(0)
            self.rollbacks += 1

    db = FakeSession()

    class Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(session_module, "AsyncSessionLocal", Factory())

    agen = session_module.get_db()
    assert await anext(agen) is db
    with pytest.raises(StopAsyncIteration):
        await anext(agen)
    assert db.commits == 1

    agen2 = session_module.get_db()
    await anext(agen2)
    with pytest.raises(RuntimeError):
        await agen2.athrow(RuntimeError("x"))
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_outbox_event_publisher_delegates(monkeypatch):
    calls = []

    async def fake_write(session, **kwargs):
        await asyncio.sleep(0)
        calls.append((session, kwargs))

    import infrastructure.publishers.outbox_event_publisher as module

    monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

    pub = OutboxEventPublisher()
    session = object()
    await pub.publish(session, uuid4(), "appointment_events", "appointment.booked", {"ok": True})

    assert len(calls) == 1
    assert calls[0][0] is session
    assert calls[0][1]["event_type"] == "appointment.booked"
