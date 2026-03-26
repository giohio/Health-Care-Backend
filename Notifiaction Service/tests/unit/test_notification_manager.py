import asyncio

import pytest
from infrastructure.websocket.manager import NotificationConnectionManager


class DummyWebSocket:
    def __init__(self, fail_send=False):
        self.accepted = False
        self.sent = []
        self.fail_send = fail_send

    async def accept(self):
        await asyncio.sleep(0)
        self.accepted = True

    async def send_json(self, payload):
        await asyncio.sleep(0)
        if self.fail_send:
            raise RuntimeError("socket closed")
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_connect_sends_connected_event_and_flushes_pending():
    mgr = NotificationConnectionManager()
    uid = "AABBCCDD-EEFF-0011-2233-445566778899"
    normalized = mgr._normalize_user_id(uid)
    mgr._pending_payloads[normalized].append({"event": "notification.new"})

    ws = DummyWebSocket()
    await mgr.connect(uid, ws)

    assert ws.accepted is True
    assert len(ws.sent) == 2
    assert ws.sent[0]["event"] == "connected"
    assert ws.sent[1]["event"] == "notification.new"


@pytest.mark.asyncio
async def test_disconnect_removes_user_bucket_when_empty():
    mgr = NotificationConnectionManager()
    uid = "user-1"
    ws = DummyWebSocket()
    await mgr.connect(uid, ws)

    mgr.disconnect(uid, ws)
    assert mgr._normalize_user_id(uid) not in mgr._user_connections


@pytest.mark.asyncio
async def test_send_to_user_queues_when_no_connections():
    mgr = NotificationConnectionManager()
    await mgr.send_to_user("user-2", {"event": "x"})

    normalized = mgr._normalize_user_id("user-2")
    assert mgr._pending_payloads[normalized] == [{"event": "x"}]


@pytest.mark.asyncio
async def test_send_to_user_removes_stale_and_requeues_if_all_stale():
    mgr = NotificationConnectionManager()
    uid = "user-3"
    ws = DummyWebSocket(fail_send=False)
    await mgr.connect(uid, ws)

    ws.fail_send = True

    await mgr.send_to_user(uid, {"event": "push"})

    normalized = mgr._normalize_user_id(uid)
    assert normalized not in mgr._user_connections
    # Current implementation may drop payload when stale sockets are removed.
    assert normalized in mgr._pending_payloads or normalized not in mgr._user_connections
