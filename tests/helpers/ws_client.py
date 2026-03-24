"""WebSocket test client for notification tests."""

import asyncio
import json
from typing import Optional

import websockets


def _to_ws_base_url(base_url: str) -> str:
    if base_url.startswith("http://"):
        return "ws://" + base_url[len("http://") :]
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://") :]
    return base_url


class WsTestClient:
    """
    Connects to Notification Service WebSocket.
    Collects all received messages.
    Use as async context manager.

    Usage:
        async with WsTestClient(url, token) as ws:
            # trigger some action
            await asyncio.sleep(2)
            msg = ws.find_message('notification.new')
            assert msg is not None
    """

    def __init__(self, base_url: str, user_id: str):
        ws_base_url = _to_ws_base_url(base_url)
        self.url = f"{ws_base_url}/ws/{user_id}"
        self.messages = []
        self._ws = None
        self._task = None

    async def __aenter__(self):
        self._ws = await websockets.connect(self.url)
        self._task = asyncio.create_task(self._receive_loop())
        return self

    async def __aexit__(self, *args):
        if self._task:
            self._task.cancel()
        if self._ws:
            await self._ws.close()

    async def _receive_loop(self):
        try:
            async for raw in self._ws:
                self.messages.append(json.loads(raw))
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass

    def find_message(self, event: str) -> Optional[dict]:
        """Find first message matching event type."""
        return next((m for m in self.messages if m.get("event") == event), None)

    def all_messages(self, event: str) -> list[dict]:
        return [m for m in self.messages if m.get("event") == event]
