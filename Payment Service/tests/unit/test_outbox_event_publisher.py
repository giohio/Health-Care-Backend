import asyncio
from uuid import uuid4

import pytest

from infrastructure.publishers.outbox_event_publisher import OutboxEventPublisher


@pytest.mark.asyncio
async def test_publish_delegates_to_outbox_writer(monkeypatch):
    calls = []

    async def fake_write(session, aggregate_id, aggregate_type, event_type, payload):
        await asyncio.sleep(0)
        calls.append(
            {
                "session": session,
                "aggregate_id": aggregate_id,
                "aggregate_type": aggregate_type,
                "event_type": event_type,
                "payload": payload,
            }
        )

    import infrastructure.publishers.outbox_event_publisher as module

    monkeypatch.setattr(module.OutboxWriter, "write", fake_write)

    publisher = OutboxEventPublisher()
    session = object()
    aggregate_id = uuid4()
    payload = {"k": "v"}

    await publisher.publish(
        session=session,
        aggregate_id=aggregate_id,
        aggregate_type="payment_events",
        event_type="payment.created",
        payload=payload,
    )

    assert len(calls) == 1
    assert calls[0]["session"] is session
    assert calls[0]["aggregate_id"] == aggregate_id
    assert calls[0]["aggregate_type"] == "payment_events"
    assert calls[0]["event_type"] == "payment.created"
    assert calls[0]["payload"] == payload
